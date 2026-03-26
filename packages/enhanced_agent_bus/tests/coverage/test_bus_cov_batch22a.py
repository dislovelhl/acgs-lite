"""
Coverage tests batch 22a: swarm_intelligence/coordinator, coordinators/swarm_coordinator,
interfaces, and registry modules.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 2. coordinators/swarm_coordinator.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.coordinators.swarm_coordinator import (
    SwarmCoordinator as CoordinatorsSwarmCoordinator,
)

# We need AgentMessage from core_models for registry tests
from enhanced_agent_bus.core_models import AgentMessage

# ---------------------------------------------------------------------------
# 3. interfaces.py  (protocol checks)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.interfaces import (
    AgentRegistry,
    CircuitBreakerProtocol,
    MACIEnforcerProtocol,
    MACIRegistryProtocol,
    MessageHandler,
    MessageProcessorProtocol,
    MessageRouter,
    MetricsCollector,
    OrchestratorProtocol,
    PolicyClientProtocol,
    PolicyValidationResultProtocol,
    ProcessingStrategy,
    RustProcessorProtocol,
    TransportProtocol,
    ValidationStrategy,
)

# ---------------------------------------------------------------------------
# 4. registry.py
# ---------------------------------------------------------------------------
from enhanced_agent_bus.registry import (
    CapabilityBasedRouter,
    DirectMessageRouter,
    InMemoryAgentRegistry,
)

# ---------------------------------------------------------------------------
# 1. swarm_intelligence/coordinator.py  (SwarmCoordinator)
# ---------------------------------------------------------------------------
from enhanced_agent_bus.swarm_intelligence.coordinator import (
    MAX_AGENT_NAME_LENGTH,
    MAX_TASK_DESCRIPTION_LENGTH,
    SwarmCoordinator,
    create_swarm_coordinator,
)
from enhanced_agent_bus.swarm_intelligence.enums import (
    AgentState,
    ConsensusType,
    TaskPriority,
)
from enhanced_agent_bus.swarm_intelligence.models import (
    AgentCapability,
    SwarmAgent,
    SwarmTask,
)

# ============================================================================
# Helpers
# ============================================================================


def _caps(*names: str) -> list[AgentCapability]:
    return [
        AgentCapability(name=n, description=f"cap-{n}", proficiency=0.9, cost_factor=1.0)
        for n in names
    ]


# ============================================================================
# SwarmCoordinator (swarm_intelligence/coordinator.py)
# ============================================================================


class TestSwarmCoordinatorSpawn:
    async def test_spawn_agent_success(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("alpha", _caps("py"))
        assert agent is not None
        assert agent.name == "alpha"
        assert agent.state == AgentState.READY

    async def test_spawn_agent_max_reached(self):
        sc = SwarmCoordinator(max_agents=1)
        first = await sc.spawn_agent("a1", _caps("py"))
        assert first is not None
        second = await sc.spawn_agent("a2", _caps("py"))
        assert second is None

    async def test_spawn_agent_empty_name_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="at least"):
            await sc.spawn_agent("", _caps("py"))

    async def test_spawn_agent_long_name_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="must not exceed"):
            await sc.spawn_agent("x" * (MAX_AGENT_NAME_LENGTH + 1), _caps("py"))

    async def test_spawn_agent_no_capabilities_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="capability"):
            await sc.spawn_agent("agent", [])


class TestSwarmCoordinatorTerminate:
    async def test_terminate_existing(self):
        sc = SwarmCoordinator()
        agent = await sc.spawn_agent("t1", _caps("py"))
        assert agent is not None
        result = await sc.terminate_agent(agent.id)
        assert result is True
        assert sc.get_agent(agent.id) is None

    async def test_terminate_nonexistent(self):
        sc = SwarmCoordinator()
        result = await sc.terminate_agent("no-such-id")
        assert result is False


class TestSwarmCoordinatorSubmitTask:
    async def test_submit_task_basic(self):
        sc = SwarmCoordinator()
        task_id = await sc.submit_task("do stuff", ["py"], decompose=False)
        assert task_id is not None
        assert sc.get_task(task_id) is not None

    async def test_submit_task_empty_desc_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="required"):
            await sc.submit_task("", ["py"])

    async def test_submit_task_too_long_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="must not exceed"):
            await sc.submit_task("x" * (MAX_TASK_DESCRIPTION_LENGTH + 1), ["py"])

    async def test_submit_task_no_capabilities_raises(self):
        sc = SwarmCoordinator()
        with pytest.raises(Exception, match="capability"):
            await sc.submit_task("do stuff", [])

    async def test_submit_task_with_decompose(self):
        sc = SwarmCoordinator()
        task_id = await sc.submit_task("code_generation for module", ["coding"], decompose=True)
        assert task_id is not None
        stats = sc.get_stats()
        assert stats["metrics"]["tasks_submitted"] >= 1


class TestSwarmCoordinatorAssignTasks:
    async def test_assign_tasks_basic(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("w1", _caps("py"))
        assert agent is not None
        await sc.submit_task("simple task", ["py"], decompose=False)
        assigned = await sc.assign_tasks()
        assert assigned == 1
        assert agent.state == AgentState.BUSY

    async def test_assign_tasks_no_matching_agent(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("w1", _caps("js"))
        await sc.submit_task("simple task", ["py"], decompose=False)
        assigned = await sc.assign_tasks()
        assert assigned == 0

    async def test_assign_tasks_with_unsatisfied_dependency(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("w1", _caps("py"))
        await sc.submit_task("task", ["py"], decompose=False, dependencies=["nonexistent"])
        assigned = await sc.assign_tasks()
        assert assigned == 0


class TestSwarmCoordinatorCompleteTask:
    async def test_complete_task_success(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("w1", _caps("py"))
        assert agent is not None
        task_id = await sc.submit_task("work", ["py"], decompose=False)
        await sc.assign_tasks()
        result = await sc.complete_task(task_id, {"done": True})
        assert result is True
        assert agent.state == AgentState.READY
        assert agent.tasks_completed == 1

    async def test_complete_task_with_error(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("w1", _caps("py"))
        assert agent is not None
        task_id = await sc.submit_task("work", ["py"], decompose=False)
        await sc.assign_tasks()
        result = await sc.complete_task(task_id, None, error="boom")
        assert result is True
        assert agent.tasks_failed == 1

    async def test_complete_nonexistent_task(self):
        sc = SwarmCoordinator()
        result = await sc.complete_task("fake-id", None)
        assert result is False


class TestSwarmCoordinatorConsensus:
    async def test_request_consensus(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("voter", _caps("py"))
        assert agent is not None
        proposal = await sc.request_consensus(agent.id, "deploy", {"env": "prod"})
        assert proposal is not None
        assert proposal.action == "deploy"

    async def test_vote_on_consensus(self):
        sc = SwarmCoordinator(max_agents=4)
        a1 = await sc.spawn_agent("v1", _caps("py"))
        a2 = await sc.spawn_agent("v2", _caps("py"))
        assert a1 is not None and a2 is not None
        proposal = await sc.request_consensus(a1.id, "act", {})
        is_decided, result = await sc.vote_on_consensus(proposal.id, a1.id, True)
        # With 2 agents, one approval may or may not reach majority
        assert isinstance(is_decided, bool)


class TestSwarmCoordinatorMessaging:
    async def test_send_message(self):
        sc = SwarmCoordinator(max_agents=4)
        a1 = await sc.spawn_agent("s1", _caps("py"))
        a2 = await sc.spawn_agent("s2", _caps("py"))
        assert a1 is not None and a2 is not None
        msg_id = await sc.send_message(a1.id, a2.id, "hello", {"text": "hi"})
        assert msg_id is not None
        assert sc.get_stats()["metrics"]["messages_sent"] == 1

    async def test_broadcast_message(self):
        sc = SwarmCoordinator(max_agents=4)
        a1 = await sc.spawn_agent("b1", _caps("py"))
        a2 = await sc.spawn_agent("b2", _caps("py"))
        assert a1 is not None and a2 is not None
        msg_id = await sc.broadcast_message(a1.id, "alert", {"level": "high"})
        assert msg_id is not None
        assert sc.get_stats()["metrics"]["messages_sent"] == 2


class TestSwarmCoordinatorHealth:
    async def test_check_health_not_found(self):
        sc = SwarmCoordinator()
        health = await sc.check_agent_health("missing")
        assert health["healthy"] is False
        assert health["status"] == "not_found"

    async def test_check_health_error_state(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("err", _caps("py"))
        assert agent is not None
        agent.state = AgentState.ERROR
        health = await sc.check_agent_health(agent.id)
        assert health["healthy"] is False
        assert health["action"] == "terminate"

    async def test_check_health_stuck_task(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("stuck", _caps("py"))
        assert agent is not None
        task_id = await sc.submit_task("work", ["py"], decompose=False)
        await sc.assign_tasks()
        # Make the task look started long ago
        task = sc.get_task(task_id)
        assert task is not None
        task.started_at = datetime.now(UTC) - timedelta(seconds=700)
        health = await sc.check_agent_health(agent.id, max_task_duration_seconds=600)
        assert health["healthy"] is False
        assert "stuck" in health["issues"][0].lower() or "Task" in health["issues"][0]

    async def test_check_health_stale_heartbeat(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("stale", _caps("py"))
        assert agent is not None
        agent.last_active = datetime.now(UTC) - timedelta(seconds=200)
        health = await sc.check_agent_health(agent.id, max_heartbeat_age_seconds=120)
        assert health["healthy"] is False
        assert health["action"] == "restart"

    async def test_check_health_high_failure_rate(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("fail", _caps("py"))
        assert agent is not None
        agent.tasks_completed = 2
        agent.tasks_failed = 5
        health = await sc.check_agent_health(agent.id)
        assert health["healthy"] is False
        assert health["action"] == "terminate"

    async def test_check_health_healthy_agent(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("ok", _caps("py"))
        assert agent is not None
        health = await sc.check_agent_health(agent.id)
        assert health["healthy"] is True


class TestSwarmCoordinatorSelfHealing:
    async def test_perform_self_healing_none_action(self):
        sc = SwarmCoordinator()
        result = await sc.perform_self_healing("x", {"action": "none"})
        assert result is False

    async def test_perform_self_healing_restart(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("r", _caps("py"))
        assert agent is not None
        agent.state = AgentState.ERROR
        result = await sc.perform_self_healing(agent.id, {"action": "restart"})
        assert result is True
        assert agent.state == AgentState.READY

    async def test_perform_self_healing_restart_task(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("rt", _caps("py"))
        assert agent is not None
        task_id = await sc.submit_task("work", ["py"], decompose=False)
        await sc.assign_tasks()
        result = await sc.perform_self_healing(agent.id, {"action": "restart_task"})
        assert result is True
        assert agent.state == AgentState.READY
        assert agent.current_task is None

    async def test_perform_self_healing_terminate(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("t", _caps("py"))
        assert agent is not None
        result = await sc.perform_self_healing(agent.id, {"action": "terminate"})
        assert result is True
        assert sc.get_agent(agent.id) is None

    async def test_perform_self_healing_unknown_action(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("u", _caps("py"))
        assert agent is not None
        result = await sc.perform_self_healing(agent.id, {"action": "unknown_action"})
        assert result is False

    async def test_perform_self_healing_agent_not_found(self):
        sc = SwarmCoordinator()
        result = await sc.perform_self_healing("missing", {"action": "restart"})
        assert result is False


class TestSwarmCoordinatorRunHealthChecks:
    async def test_run_health_checks_with_auto_heal(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("hc", _caps("py"))
        assert agent is not None
        agent.state = AgentState.ERROR
        results = await sc.run_health_checks(auto_heal=True)
        assert len(results) >= 1
        # After auto-heal with ERROR state, agent should be terminated
        assert sc.get_agent(agent.id) is None

    async def test_run_health_checks_no_auto_heal(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("hc2", _caps("py"))
        assert agent is not None
        agent.state = AgentState.ERROR
        results = await sc.run_health_checks(auto_heal=False)
        assert len(results) >= 1
        # Agent should still exist since auto_heal is off
        assert sc.get_agent(agent.id) is not None


class TestSwarmCoordinatorMisc:
    async def test_update_agent_heartbeat(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("hb", _caps("py"))
        assert agent is not None
        old_active = agent.last_active
        await asyncio.sleep(0.01)
        result = await sc.update_agent_heartbeat(agent.id)
        assert result is True
        assert agent.last_active >= old_active

    async def test_update_agent_heartbeat_missing(self):
        sc = SwarmCoordinator()
        result = await sc.update_agent_heartbeat("missing")
        assert result is False

    async def test_get_active_agents(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("a1", _caps("py"))
        active = sc.get_active_agents()
        assert len(active) == 1

    async def test_get_available_agents(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("a1", _caps("py"))
        assert agent is not None
        avail = sc.get_available_agents()
        assert len(avail) == 1
        agent.state = AgentState.BUSY
        avail = sc.get_available_agents()
        assert len(avail) == 0

    async def test_get_health_stats(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("h1", _caps("py"))
        stats = sc.get_health_stats()
        assert stats["total_agents"] == 1
        assert stats["healthy_agents"] == 1

    async def test_get_health_stats_with_error_agent(self):
        sc = SwarmCoordinator(max_agents=4)
        agent = await sc.spawn_agent("h1", _caps("py"))
        assert agent is not None
        agent.state = AgentState.ERROR
        stats = sc.get_health_stats()
        assert stats["unhealthy_agents"] == 1

    async def test_get_health_stats_empty(self):
        sc = SwarmCoordinator()
        stats = sc.get_health_stats()
        assert stats["health_ratio"] == 0.0

    async def test_get_stats(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("s1", _caps("py"))
        stats = sc.get_stats()
        assert stats["total_agents"] == 1
        assert "constitutional_hash" in stats

    async def test_get_dashboard_metrics(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("d1", _caps("py"))
        metrics = await sc.get_dashboard_metrics()
        assert "agents" in metrics
        assert "tasks" in metrics
        assert "consensus" in metrics
        assert "messaging" in metrics
        assert "lifecycle" in metrics
        assert "health" in metrics
        assert metrics["version"] == "3.1"

    async def test_shutdown(self):
        sc = SwarmCoordinator(max_agents=4)
        await sc.spawn_agent("s1", _caps("py"))
        await sc.spawn_agent("s2", _caps("py"))
        await sc.shutdown()
        assert len(sc.get_active_agents()) == 0

    def test_create_swarm_coordinator_factory(self):
        sc = create_swarm_coordinator(max_agents=5)
        assert isinstance(sc, SwarmCoordinator)
        assert sc.max_agents == 5


class TestSwarmCoordinatorDependencies:
    async def test_dependencies_satisfied_true(self):
        sc = SwarmCoordinator(max_agents=4)
        dep_id = await sc.submit_task("dep", ["py"], decompose=False)
        await sc.spawn_agent("w", _caps("py"))
        await sc.assign_tasks()
        await sc.complete_task(dep_id, "ok")

        main_id = await sc.submit_task("main", ["py"], decompose=False, dependencies=[dep_id])
        task = sc.get_task(main_id)
        assert task is not None
        assert sc._dependencies_satisfied(task) is True

    async def test_dependencies_satisfied_false(self):
        sc = SwarmCoordinator()
        task = SwarmTask(
            id="t1",
            description="test",
            required_capabilities=["py"],
            dependencies=["nonexistent"],
        )
        assert sc._dependencies_satisfied(task) is False


# ============================================================================
# CoordinatorsSwarmCoordinator (coordinators/swarm_coordinator.py)
# ============================================================================


class TestCoordinatorsSwarmCoordinator:
    def test_init_with_swarm_import_failure(self):
        """Test fallback when swarm_intelligence is not importable."""
        with patch.object(
            CoordinatorsSwarmCoordinator,
            "_initialize_swarm",
        ):
            coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
            coord._max_agents = 10
            coord._enable_consensus = True
            coord._swarm = None
            coord._initialized = False
            coord._agents = {}
            assert coord.is_available is False

    async def test_spawn_agent_fallback_no_swarm(self):
        """When swarm is not available, use dict-based agent storage."""
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {}
        result = await coord.spawn_agent("worker", ["py", "analysis"])
        assert result is not None
        assert result["type"] == "worker"
        assert result["capabilities"] == ["py", "analysis"]
        assert result["state"] == "ready"
        assert "constitutional_hash" in result

    async def test_spawn_agent_with_name(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {}
        result = await coord.spawn_agent("worker", ["py"], name="custom-name")
        assert result is not None
        assert result["name"] == "custom-name"

    async def test_spawn_agent_swarm_available_error(self):
        """When swarm raises, return None."""
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._initialized = True
        coord._agents = {}
        mock_swarm = MagicMock()
        mock_swarm.spawn_agent = AsyncMock(side_effect=RuntimeError("fail"))
        coord._swarm = mock_swarm
        result = await coord.spawn_agent("worker", ["py"])
        assert result is None

    async def test_route_task_fallback(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {
            "a1": {"id": "a1", "name": "worker1", "capabilities": ["py", "js"]},
            "a2": {"id": "a2", "name": "worker2", "capabilities": ["go"]},
        }
        result = await coord.route_task("build API", ["py"])
        assert len(result) == 1
        assert result[0]["id"] == "a1"
        assert result[0]["match_score"] == 1.0

    async def test_route_task_fallback_no_match(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {
            "a1": {"id": "a1", "name": "worker1", "capabilities": ["go"]},
        }
        result = await coord.route_task("build API", ["py"])
        assert len(result) == 0

    async def test_route_task_swarm_error_falls_back(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._initialized = True
        coord._agents = {
            "a1": {"id": "a1", "name": "worker1", "capabilities": ["py"]},
        }
        mock_swarm = MagicMock()
        mock_swarm.route_task = AsyncMock(side_effect=RuntimeError("fail"))
        coord._swarm = mock_swarm
        result = await coord.route_task("do stuff", ["py"])
        assert len(result) == 1

    async def test_terminate_agent_exists(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {"a1": {"id": "a1", "name": "w"}}
        result = await coord.terminate_agent("a1")
        assert result is True
        assert "a1" not in coord._agents

    async def test_terminate_agent_not_exists(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {}
        result = await coord.terminate_agent("missing")
        assert result is False

    async def test_terminate_agent_with_swarm_error(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._initialized = True
        mock_swarm = MagicMock()
        mock_swarm.terminate_agent = AsyncMock(side_effect=RuntimeError("fail"))
        coord._swarm = mock_swarm
        coord._agents = {"a1": {"id": "a1", "name": "w"}}
        result = await coord.terminate_agent("a1")
        assert result is True

    def test_get_active_agents_dict(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        coord._agents = {
            "a1": {"id": "a1", "name": "w1", "capabilities": ["py"]},
        }
        result = coord.get_active_agents()
        assert result["active_count"] == 1
        assert result["swarm_available"] is False
        assert len(result["agents"]) == 1

    def test_get_active_agents_object(self):
        """Test with SwarmAgent objects instead of dicts."""
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        agent = SwarmAgent(id="a1", name="w1", capabilities=_caps("py"), state=AgentState.READY)
        coord._agents = {"a1": agent}
        result = coord.get_active_agents()
        assert result["active_count"] == 1
        assert result["agents"][0]["name"] == "w1"

    def test_is_available_true(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._initialized = True
        coord._swarm = MagicMock()
        assert coord.is_available is True

    def test_is_available_false(self):
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._initialized = False
        coord._swarm = None
        assert coord.is_available is False

    async def test_route_task_with_object_agent(self):
        """Route fallback with SwarmAgent objects (not dicts)."""
        coord = CoordinatorsSwarmCoordinator.__new__(CoordinatorsSwarmCoordinator)
        coord._max_agents = 10
        coord._enable_consensus = True
        coord._swarm = None
        coord._initialized = False
        agent = SwarmAgent(
            id="a1", name="w1", capabilities=_caps("py", "js"), state=AgentState.READY
        )
        coord._agents = {"a1": agent}
        result = await coord.route_task("do stuff", ["py"])
        assert len(result) == 1
        assert result[0]["name"] == "w1"


# ============================================================================
# Interfaces (interfaces.py) - Protocol compliance tests
# ============================================================================


class _MockRegistry:
    async def register(self, agent_id, capabilities=None, metadata=None):
        return True

    async def unregister(self, agent_id):
        return True

    async def get(self, agent_id):
        return {"agent_id": agent_id}

    async def list_agents(self):
        return ["a1"]

    async def exists(self, agent_id):
        return True

    async def update_metadata(self, agent_id, metadata):
        return True


class _MockRouter:
    async def route(self, message, registry):
        return "target"

    async def broadcast(self, message, registry, exclude=None):
        return ["a1"]


class _MockValidation:
    async def validate(self, message):
        return (True, None)


class _MockProcessingStrategy:
    async def process(self, message, handlers):
        return MagicMock(is_valid=True)

    def is_available(self):
        return True

    def get_name(self):
        return "mock"


class _MockMessageHandler:
    async def handle(self, message):
        return None

    def can_handle(self, message):
        return True


class _MockMetrics:
    def record_message_processed(self, message_type, duration_ms, success):
        pass

    def record_agent_registered(self, agent_id):
        pass

    def record_agent_unregistered(self, agent_id):
        pass

    def get_metrics(self):
        return {}


class _MockMessageProcessor:
    async def process(self, message):
        return MagicMock(is_valid=True)


class _MockMACIRegistry:
    def register_agent(self, agent_id, role):
        return True

    def get_role(self, agent_id):
        return "executive"

    def unregister_agent(self, agent_id):
        return True


class _MockMACIEnforcer:
    async def validate_action(self, agent_id, action, target_output_id=None):
        return {"valid": True}


class _MockTransport:
    async def start(self):
        pass

    async def stop(self):
        pass

    async def send(self, message, topic=None):
        return True

    async def subscribe(self, topic, handler):
        pass


class _MockOrchestrator:
    async def start(self):
        pass

    async def stop(self):
        pass

    def get_status(self):
        return {"status": "running"}


class _MockCircuitBreaker:
    async def record_success(self):
        pass

    async def record_failure(self, error=None, error_type="unknown"):
        pass

    async def can_execute(self):
        return True

    async def reset(self):
        pass


class _MockPolicyValidationResult:
    @property
    def is_valid(self):
        return True

    @property
    def errors(self):
        return []


class _MockPolicyClient:
    async def validate_message_signature(self, message):
        return _MockPolicyValidationResult()


class _MockRustProcessor:
    def validate(self, message):
        return True


class TestInterfaceProtocols:
    def test_agent_registry_protocol(self):
        assert isinstance(_MockRegistry(), AgentRegistry)

    def test_message_router_protocol(self):
        assert isinstance(_MockRouter(), MessageRouter)

    def test_validation_strategy_protocol(self):
        assert isinstance(_MockValidation(), ValidationStrategy)

    def test_processing_strategy_protocol(self):
        assert isinstance(_MockProcessingStrategy(), ProcessingStrategy)

    def test_message_handler_protocol(self):
        assert isinstance(_MockMessageHandler(), MessageHandler)

    def test_metrics_collector_protocol(self):
        assert isinstance(_MockMetrics(), MetricsCollector)

    def test_message_processor_protocol(self):
        assert isinstance(_MockMessageProcessor(), MessageProcessorProtocol)

    def test_maci_registry_protocol(self):
        assert isinstance(_MockMACIRegistry(), MACIRegistryProtocol)

    def test_maci_enforcer_protocol(self):
        assert isinstance(_MockMACIEnforcer(), MACIEnforcerProtocol)

    def test_transport_protocol(self):
        assert isinstance(_MockTransport(), TransportProtocol)

    def test_orchestrator_protocol(self):
        assert isinstance(_MockOrchestrator(), OrchestratorProtocol)

    def test_circuit_breaker_protocol(self):
        assert isinstance(_MockCircuitBreaker(), CircuitBreakerProtocol)

    def test_policy_validation_result_protocol(self):
        assert isinstance(_MockPolicyValidationResult(), PolicyValidationResultProtocol)

    def test_policy_client_protocol(self):
        assert isinstance(_MockPolicyClient(), PolicyClientProtocol)

    def test_rust_processor_protocol(self):
        assert isinstance(_MockRustProcessor(), RustProcessorProtocol)

    def test_non_compliant_not_instance(self):
        """A plain object should not satisfy any protocol."""

        class _Empty:
            pass

        assert not isinstance(_Empty(), AgentRegistry)
        assert not isinstance(_Empty(), MessageRouter)
        assert not isinstance(_Empty(), ValidationStrategy)
        assert not isinstance(_Empty(), MetricsCollector)


# ============================================================================
# Registry (registry.py) - InMemoryAgentRegistry, DirectMessageRouter,
# CapabilityBasedRouter
# ============================================================================


class TestInMemoryAgentRegistry:
    async def test_register_and_get(self):
        reg = InMemoryAgentRegistry()
        ok = await reg.register("a1", capabilities=["py"])
        assert ok is True
        info = await reg.get("a1")
        assert info is not None
        assert info["agent_id"] == "a1"

    async def test_register_duplicate(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        ok = await reg.register("a1")
        assert ok is False

    async def test_unregister(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        ok = await reg.unregister("a1")
        assert ok is True
        assert await reg.get("a1") is None

    async def test_unregister_missing(self):
        reg = InMemoryAgentRegistry()
        ok = await reg.unregister("missing")
        assert ok is False

    async def test_list_agents(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        agents = await reg.list_agents()
        assert set(agents) == {"a1", "a2"}

    async def test_exists(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        assert await reg.exists("a1") is True
        assert await reg.exists("a2") is False

    async def test_update_metadata(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", metadata={"role": "worker"})
        ok = await reg.update_metadata("a1", {"role": "manager"})
        assert ok is True
        info = await reg.get("a1")
        assert info is not None
        assert info["metadata"]["role"] == "manager"

    async def test_update_metadata_missing(self):
        reg = InMemoryAgentRegistry()
        ok = await reg.update_metadata("missing", {"x": 1})
        assert ok is False

    async def test_clear(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.clear()
        assert reg.agent_count == 0

    async def test_agent_count(self):
        reg = InMemoryAgentRegistry()
        assert reg.agent_count == 0
        await reg.register("a1")
        assert reg.agent_count == 1


class TestDirectMessageRouter:
    async def test_route_to_existing_agent(self):
        reg = InMemoryAgentRegistry()
        await reg.register("target", metadata={"tenant_id": "t1"})
        router = DirectMessageRouter()
        msg = AgentMessage(to_agent="target", tenant_id="t1")
        result = await router.route(msg, reg)
        assert result == "target"

    async def test_route_no_target(self):
        reg = InMemoryAgentRegistry()
        router = DirectMessageRouter()
        msg = AgentMessage(to_agent="")
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_agent_not_found(self):
        reg = InMemoryAgentRegistry()
        router = DirectMessageRouter()
        msg = AgentMessage(to_agent="missing")
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_tenant_mismatch(self):
        reg = InMemoryAgentRegistry()
        await reg.register("target", metadata={"tenant_id": "t1"})
        router = DirectMessageRouter()
        msg = AgentMessage(to_agent="target", tenant_id="t2")
        result = await router.route(msg, reg)
        assert result is None

    async def test_broadcast(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        router = DirectMessageRouter()
        msg = AgentMessage(from_agent="a1")
        result = await router.broadcast(msg, reg)
        assert "a2" in result
        assert "a1" not in result

    async def test_broadcast_with_exclude(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1")
        await reg.register("a2")
        await reg.register("a3")
        router = DirectMessageRouter()
        msg = AgentMessage(from_agent="a1")
        result = await router.broadcast(msg, reg, exclude=["a2"])
        assert "a3" in result
        assert "a1" not in result
        assert "a2" not in result


class TestCapabilityBasedRouter:
    async def test_route_direct_target(self):
        reg = InMemoryAgentRegistry()
        await reg.register("target", capabilities=["py"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(to_agent="target")
        result = await router.route(msg, reg)
        assert result == "target"

    async def test_route_by_capability(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py", "js"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(
            to_agent="",
            content={"required_capabilities": ["py"]},
        )
        result = await router.route(msg, reg)
        assert result == "a1"

    async def test_route_no_match(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["go"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(
            to_agent="",
            content={"required_capabilities": ["py"]},
        )
        result = await router.route(msg, reg)
        assert result is None

    async def test_route_no_capabilities_required(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(to_agent="", content={})
        result = await router.route(msg, reg)
        assert result is None

    async def test_broadcast_with_capabilities(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py", "js"])
        await reg.register("a2", capabilities=["go"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(
            from_agent="sender",
            content={"required_capabilities": ["py"]},
        )
        result = await router.broadcast(msg, reg)
        assert "a1" in result
        assert "a2" not in result

    async def test_broadcast_no_capabilities(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py"])
        await reg.register("a2", capabilities=["go"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(from_agent="sender", content={})
        result = await router.broadcast(msg, reg)
        assert len(result) == 2

    async def test_broadcast_with_exclude(self):
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py"])
        await reg.register("a2", capabilities=["py"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(
            from_agent="sender",
            content={"required_capabilities": ["py"]},
        )
        result = await router.broadcast(msg, reg, exclude=["a1"])
        assert "a1" not in result
        assert "a2" in result

    async def test_route_non_dict_content(self):
        """When content is not a dict, no capabilities are extracted."""
        reg = InMemoryAgentRegistry()
        await reg.register("a1", capabilities=["py"])
        router = CapabilityBasedRouter()
        msg = AgentMessage(to_agent="")
        # Force content to a non-dict for this edge case
        msg.content = "plain text"  # type: ignore[assignment]
        result = await router.route(msg, reg)
        assert result is None
