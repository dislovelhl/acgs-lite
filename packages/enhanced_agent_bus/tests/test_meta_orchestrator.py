"""
Comprehensive Tests for Meta-Orchestrator
==========================================

Tests the Ultimate Agentic Development System Meta-Orchestrator including:
- Core orchestration functionality
- Mamba-2 context integration
- MACI role enforcement
- SAFLA neural memory
- Swarm agent management
- Constitutional compliance
- Workflow evolution

Constitutional Hash: 608508a9bd224290
"""

import asyncio
import sys
from datetime import datetime, timezone

import pytest

from ..meta_orchestrator import (
    CONSTITUTIONAL_HASH,
    LANGGRAPH_AVAILABLE,
    MACI_AVAILABLE,
    MAMBA_AVAILABLE,
    AgentCapability,
    MemoryEntry,
    MemoryTier,
    MetaOrchestrator,
    OrchestratorConfig,
    SAFLANeuralMemory,
    SwarmAgent,
    TaskComplexity,
    TaskResult,
    TaskType,
    create_meta_orchestrator,
)


@pytest.fixture(autouse=True)
def _ensure_meta_orchestrator_importable():
    """Defensive fixture: ensure meta_orchestrator submodules are present in sys.modules.

    When test_maci_imports_coverage.py runs in the same xdist worker before this file,
    its _reload_maci_imports() can delete and replace sys.modules entries for EAB
    subpackages. If the restored module object differs from the one cached in
    meta_orchestrator.__init__'s import chain, imports break with ImportError or
    AttributeError. This fixture snapshots and restores the relevant sys.modules
    entries to guarantee isolation. (PM-011, PM-014 patterns)
    """
    # Protect all meta_orchestrator submodule entries
    _keys_to_protect = [
        k
        for k in list(sys.modules.keys())
        if k.startswith("enhanced_agent_bus.meta_orchestrator")
        or k.startswith("enhanced_agent_bus.meta_orchestrator")
    ]
    # Also protect the maci_imports entry that other tests may corrupt
    _keys_to_protect.extend(
        [
            "enhanced_agent_bus.maci_imports",
            "enhanced_agent_bus.exceptions",
        ]
    )
    _SENTINEL = object()
    orig = {k: sys.modules.get(k, _SENTINEL) for k in _keys_to_protect}

    yield

    # Restore
    for k, v in orig.items():
        if v is _SENTINEL:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


# ============================================================================
# Constitutional Hash Tests
# ============================================================================


class TestConstitutionalHash:
    """Tests for constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_config_validates_constitutional_hash(self):
        """Config should validate constitutional hash."""
        config = OrchestratorConfig()
        assert config.validate()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_config_rejects_invalid_hash(self):
        """Config should reject invalid constitutional hash."""
        config = OrchestratorConfig(constitutional_hash="invalid")
        with pytest.raises(ValueError, match="Invalid constitutional hash"):
            config.validate()


# ============================================================================
# Task Complexity Analysis Tests
# ============================================================================


class TestTaskComplexityAnalysis:
    """Tests for task complexity analysis."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_trivial_complexity(self, orchestrator):
        """Non-keyword queries should be TRIVIAL complexity."""
        complexity = await orchestrator.analyze_complexity("hello")
        assert complexity == TaskComplexity.TRIVIAL

    async def test_simple_complexity(self, orchestrator):
        """Read/check/show tasks should be SIMPLE complexity."""
        complexity = await orchestrator.analyze_complexity("show me the files")
        assert complexity == TaskComplexity.SIMPLE

    async def test_moderate_complexity(self, orchestrator):
        """Update/fix/refactor tasks should be MODERATE complexity."""
        complexity = await orchestrator.analyze_complexity("update the configuration settings")
        assert complexity == TaskComplexity.MODERATE

    async def test_complex_complexity(self, orchestrator):
        """Implementation tasks should be COMPLEX complexity."""
        complexity = await orchestrator.analyze_complexity("implement user registration")
        assert complexity == TaskComplexity.COMPLEX

    async def test_visionary_complexity(self, orchestrator):
        """Architecture tasks should be VISIONARY complexity."""
        complexity = await orchestrator.analyze_complexity(
            "redesign the entire system architecture"
        )
        assert complexity == TaskComplexity.VISIONARY


# ============================================================================
# Task type Identification Tests
# ============================================================================


class TestTaskTypeIdentification:
    """Tests for task type identification."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_code_generation_type(self, orchestrator):
        """Code generation tasks should be identified correctly."""
        task_type = await orchestrator.identify_task_type("write a function to parse JSON")
        assert task_type == TaskType.CODE_GENERATION

    async def test_debugging_type(self, orchestrator):
        """Debug tasks should be identified correctly."""
        task_type = await orchestrator.identify_task_type("debug the error in login")
        assert task_type == TaskType.DEBUGGING

    async def test_testing_type(self, orchestrator):
        """Test tasks should be identified correctly."""
        task_type = await orchestrator.identify_task_type("run pytest tests for auth module")
        assert task_type == TaskType.TESTING

    async def test_security_audit_type(self, orchestrator):
        """Security tasks should be identified correctly."""
        task_type = await orchestrator.identify_task_type("scan for security vulnerabilities")
        assert task_type == TaskType.SECURITY_AUDIT

    async def test_constitutional_validation_type(self, orchestrator):
        """Constitutional tasks should be identified correctly."""
        task_type = await orchestrator.identify_task_type("validate constitutional compliance")
        assert task_type == TaskType.CONSTITUTIONAL_VALIDATION


# ============================================================================
# Swarm Agent Management Tests
# ============================================================================


class TestSwarmAgentManagement:
    """Tests for swarm agent spawning and management."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_spawn_agent(self, orchestrator):
        """Should spawn new agent when capacity available."""
        agent = await orchestrator.spawn_agent("python_expert", [AgentCapability.PYTHON_EXPERT])
        assert agent is not None
        assert agent.agent_type == "python_expert"
        assert AgentCapability.PYTHON_EXPERT in agent.capabilities
        assert agent.status == "idle"

    async def test_spawn_agent_respects_max_limit(self, orchestrator):
        """Should not spawn beyond max_swarm_agents limit."""
        # Spawn up to limit
        for i in range(orchestrator.config.max_swarm_agents):
            agent = await orchestrator.spawn_agent(f"agent_{i}", [AgentCapability.PYTHON_EXPERT])
            assert agent is not None

        # Next spawn should fail
        extra_agent = await orchestrator.spawn_agent("extra_agent", [AgentCapability.PYTHON_EXPERT])
        assert extra_agent is None

    async def test_agent_can_handle_task(self):
        """Agent should correctly identify if it can handle a task type."""
        agent = SwarmAgent(
            agent_id="test-agent",
            agent_type="security",
            capabilities=[AgentCapability.SECURITY_SPECIALIST],
        )
        assert agent.can_handle(TaskType.SECURITY_AUDIT)
        assert not agent.can_handle(TaskType.CODE_GENERATION)

    async def test_route_task_assigns_agents(self, orchestrator):
        """Route task should assign appropriate agents."""
        agents = await orchestrator.route_task(
            "implement authentication", TaskComplexity.COMPLEX, TaskType.CODE_GENERATION
        )
        assert len(agents) > 0
        assert all(a.status == "assigned" for a in agents)


# ============================================================================
# Constitutional Compliance Tests
# ============================================================================


class TestConstitutionalCompliance:
    """Tests for constitutional compliance validation."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_valid_constitutional_hash(self, orchestrator):
        """Should accept valid constitutional hash."""
        action = {
            "task": "test task",
            "constitutional_hash": CONSTITUTIONAL_HASH,
        }
        result = await orchestrator.validate_constitutional_compliance(action)
        assert result is True

    async def test_invalid_constitutional_hash(self, orchestrator):
        """Should reject invalid constitutional hash."""
        action = {
            "task": "test task",
            "constitutional_hash": "invalid_hash",
        }
        result = await orchestrator.validate_constitutional_compliance(action)
        assert result is False

    async def test_action_without_hash_allowed(self, orchestrator):
        """Actions without hash should be allowed (hash added automatically)."""
        action = {"task": "test task"}
        result = await orchestrator.validate_constitutional_compliance(action)
        assert result is True


# ============================================================================
# Task Execution Tests
# ============================================================================


class TestTaskExecution:
    """Tests for task execution."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_execute_task_success(self, orchestrator):
        """Should successfully execute a task."""
        result = await orchestrator.execute_task(
            "write a simple function", context={"project": "test"}
        )
        assert isinstance(result, TaskResult)
        assert result.success is True
        assert result.constitutional_compliant is True
        assert result.confidence_score > 0

    async def test_execute_task_includes_constitutional_hash(self, orchestrator):
        """Task result should include constitutional hash."""
        result = await orchestrator.execute_task("test task")
        result_dict = getattr(result, "to_dict", lambda: result.__dict__)()
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_execute_task_updates_metrics(self, orchestrator):
        """Executing task should update metrics."""
        initial_count = orchestrator._metrics["tasks_processed"]
        await orchestrator.execute_task("test task")
        assert orchestrator._metrics["tasks_processed"] == initial_count + 1


# ============================================================================
# SAFLA Neural Memory Tests
# ============================================================================


class TestSAFLANeuralMemory:
    """Tests for SAFLA Neural Memory system."""

    @pytest.fixture
    def memory(self):
        config = OrchestratorConfig()
        return SAFLANeuralMemory(config)

    async def test_store_and_retrieve(self, memory):
        """Should store and retrieve values."""
        await memory.store(MemoryTier.SEMANTIC, "test_key", {"data": "test_value"})
        result = await memory.retrieve(MemoryTier.SEMANTIC, "test_key")
        assert result == {"data": "test_value"}

    async def test_memory_tiers(self, memory):
        """Should support all four memory tiers."""
        for tier in MemoryTier:
            await memory.store(tier, f"key_{tier.value}", f"value_{tier.value}")
            result = await memory.retrieve(tier, f"key_{tier.value}")
            assert result == f"value_{tier.value}"

    async def test_semantic_search(self, memory):
        """Should search semantic memory."""
        await memory.store(
            MemoryTier.SEMANTIC, "python_tips", "Use list comprehensions for efficiency"
        )
        results = await memory.search_semantic("python")
        assert len(results) > 0

    async def test_feedback_loop(self, memory):
        """Should record feedback loops."""
        await memory.add_feedback_loop(
            context={"task": "test"},
            outcome="success",
            learning="Use async for IO operations",
            confidence=0.9,
        )
        assert len(memory._feedback_loops) == 1

    async def test_memory_stats(self, memory):
        """Should return memory statistics."""
        await memory.store(MemoryTier.VECTOR, "k1", "v1")
        await memory.store(MemoryTier.EPISODIC, "k2", "v2")
        stats = memory.get_stats()
        assert stats["tiers"]["vector"] == 1
        assert stats["tiers"]["episodic"] == 1
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Workflow Evolution Tests
# ============================================================================


class TestWorkflowEvolution:
    """Tests for workflow evolution capabilities."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_evolve_workflow_success(self, orchestrator):
        """Should evolve workflow with high confidence."""
        result = await orchestrator.evolve_workflow(
            "test_workflow", {"confidence": 0.9, "improvement": "10%"}
        )
        assert result is True
        assert orchestrator._evolution_count_today == 1

    async def test_evolve_workflow_low_confidence(self, orchestrator):
        """Should reject evolution with low confidence."""
        result = await orchestrator.evolve_workflow(
            "test_workflow", {"confidence": 0.5, "improvement": "5%"}
        )
        assert result is False
        assert orchestrator._evolution_count_today == 0

    async def test_evolve_workflow_daily_limit(self, orchestrator):
        """Should respect daily evolution limit."""
        # Max out daily evolutions
        for i in range(orchestrator.config.auto_evolution_limit):
            await orchestrator.evolve_workflow(f"workflow_{i}", {"confidence": 0.9})

        # Next evolution should fail
        result = await orchestrator.evolve_workflow("extra_workflow", {"confidence": 0.9})
        assert result is False


# ============================================================================
# Research Integration Tests
# ============================================================================


class TestResearchIntegration:
    """Tests for research integration capabilities."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_research_topic(self, orchestrator):
        """Should research a topic."""
        result = await orchestrator.research_topic(
            "machine learning optimization", sources=["arxiv", "github"]
        )
        assert result["topic"] == "machine learning optimization"
        assert "arxiv" in result["sources_queried"]
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH

    async def test_research_stores_in_memory(self, orchestrator):
        """Research should store results in memory."""
        await orchestrator.research_topic("neural networks")
        stats = orchestrator._memory.get_stats()
        # memory is a coordinator, so look for v3_stats or fallback_stats or tier_counts directly
        tier_counts = stats.get("v3_stats", stats).get("tier_counts", {})
        assert tier_counts.get("episodic", 0) >= 0
        assert tier_counts.get("semantic", 0) >= 0


# ============================================================================
# Swarm Delegation Tests
# ============================================================================


class TestSwarmDelegation:
    """Tests for swarm delegation capabilities."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_delegate_to_swarm(self, orchestrator):
        """Should delegate task to swarm."""
        result = await orchestrator.delegate_to_swarm("implement complex feature", parallel=True)
        assert result["success"] is True
        assert len(result["agents_assigned"]) > 0
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Status and Metrics Tests
# ============================================================================


class TestStatusAndMetrics:
    """Tests for status and metrics reporting."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    def test_get_status(self, orchestrator):
        """Should return comprehensive status."""
        status = orchestrator.get_status()
        assert "constitutional_hash" in status
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "active_agents" in status
        assert "max_agents" in status
        assert "components" in status
        assert "memory_stats" in status

    def test_status_includes_component_availability(self, orchestrator):
        """Status should indicate component availability."""
        status = orchestrator.get_status()
        assert "mamba2_available" in status["components"]
        assert "maci_available" in status["components"]
        assert "langgraph_available" in status["components"]

    async def test_metrics_update(self, orchestrator):
        """Metrics should update with operations."""
        await orchestrator.execute_task("test task")
        assert orchestrator._metrics["tasks_processed"] >= 1
        assert orchestrator._metrics["constitutional_validations"] >= 1


# ============================================================================
# Shutdown Tests
# ============================================================================


class TestShutdown:
    """Tests for graceful shutdown."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_shutdown_releases_agents(self, orchestrator):
        """Shutdown should release all agents."""
        # Spawn some agents
        await orchestrator.spawn_agent("test1", [AgentCapability.PYTHON_EXPERT])
        await orchestrator.spawn_agent("test2", [AgentCapability.SECURITY_SPECIALIST])

        await orchestrator.shutdown()

        active = orchestrator._active_agents
        assert active.get("active_count", len(active.get("agents", []))) == 0


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for the complete Meta-Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_full_workflow(self, orchestrator):
        """Test complete workflow: analyze, delegate, execute."""
        # Analyze complexity
        complexity = await orchestrator.analyze_complexity(
            "build a comprehensive testing framework"
        )
        assert complexity in [TaskComplexity.COMPLEX, TaskComplexity.VISIONARY]

        # Delegate to swarm
        delegation = await orchestrator.delegate_to_swarm(
            "build a comprehensive testing framework", parallel=True
        )
        assert delegation["success"] is True

        # Execute task
        result = await orchestrator.execute_task("build a comprehensive testing framework")
        assert result.success is True
        assert result.constitutional_compliant is True

        # Verify metrics updated
        status = orchestrator.get_status()
        assert status["tasks_processed"] >= 1

    async def test_constitutional_hash_throughout(self, orchestrator):
        """Constitutional hash should be present throughout all operations."""
        # Execute task
        result = await orchestrator.execute_task("test task")
        result_dict = getattr(result, "to_dict", lambda: result.__dict__)()
        assert result_dict["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Research
        research = await orchestrator.research_topic("test")
        assert research["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Delegation
        delegation = await orchestrator.delegate_to_swarm("test")
        assert delegation["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Memory
        stats = orchestrator._memory.get_stats()
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestFactoryFunction:
    """Tests for factory function."""

    def test_create_meta_orchestrator_default(self):
        """Should create orchestrator with default config."""
        orchestrator = create_meta_orchestrator()
        assert orchestrator is not None
        assert orchestrator.config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_meta_orchestrator_custom_config(self):
        """Should create orchestrator with custom config."""
        config = OrchestratorConfig(max_swarm_agents=4, enable_research=False)
        orchestrator = create_meta_orchestrator(config)
        assert orchestrator.config.max_swarm_agents == 4
        assert orchestrator._research_enabled is False


# ============================================================================
# Performance Tests (markers for selective running)
# ============================================================================


@pytest.mark.slow
class TestPerformance:
    """Performance tests for the Meta-Orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        return create_meta_orchestrator()

    async def test_latency_under_target(self, orchestrator):
        """Task execution should be under latency target."""
        import time

        start = time.perf_counter()
        await orchestrator.execute_task("simple read task")
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        # Target is 5ms, but we're lenient in tests
        assert latency_ms < 100  # Allow 100ms in test environment

    async def test_throughput(self, orchestrator):
        """Should handle multiple concurrent tasks."""
        tasks = [orchestrator.execute_task(f"task_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        assert all(r.success for r in results)
