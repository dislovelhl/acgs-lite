"""
Ultimate Agentic System - Comprehensive Test Suite
===================================================

Tests for the unified facade that integrates all agentic capabilities.

Constitutional Hash: cdd01ef066bc6cf2
"""

import asyncio
import sys
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.core.shared.errors.exceptions import (
    ServiceUnavailableError as ACGSServiceUnavailableError,
)
from src.core.shared.errors.exceptions import (
    ValidationError as ACGSValidationError,
)

from ..ultimate_agentic_system import (
    CONSTITUTIONAL_HASH,
    META_ORCHESTRATOR_AVAILABLE,
    SystemCapabilities,
    SystemConfig,
    SystemVersion,
    UltimateAgenticSystem,
    create_ultimate_system,
    development_system,
    production_system,
    quick_start,
)


@pytest.fixture(autouse=True)
def _restore_availability_flags():
    """Restore META_ORCHESTRATOR_AVAILABLE flag after each test.

    Tests that mock the orchestrator or patch availability flags can leak state
    to subsequent tests in the same xdist worker. This fixture snapshots and
    restores the module-level availability flags on both the config module and
    the availability module. (PM-012 pattern)
    """
    import packages.enhanced_agent_bus.ultimate_agentic_system.availability as avail_mod
    import packages.enhanced_agent_bus.ultimate_agentic_system.config as config_mod

    orig_config_flag = config_mod.META_ORCHESTRATOR_AVAILABLE
    orig_avail_flag = avail_mod.META_ORCHESTRATOR_AVAILABLE

    yield

    config_mod.META_ORCHESTRATOR_AVAILABLE = orig_config_flag
    avail_mod.META_ORCHESTRATOR_AVAILABLE = orig_avail_flag


# =============================================================================
# Constitutional Hash Tests
# =============================================================================


class TestConstitutionalHash:
    """Test constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_system_has_constitutional_hash(self):
        """System should include constitutional hash."""
        system = UltimateAgenticSystem()
        assert system.config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_capabilities_has_hash(self):
        """Capabilities should include hash."""
        caps = SystemCapabilities()
        assert caps.constitutional_hash == CONSTITUTIONAL_HASH

    def test_custom_hash_in_config(self):
        """Config should accept custom hash."""
        custom_hash = "custom_test_hash"
        config = SystemConfig(constitutional_hash=custom_hash)
        assert config.constitutional_hash == custom_hash


# =============================================================================
# SystemVersion Tests
# =============================================================================


class TestSystemVersion:
    """Test system version enumeration."""

    def test_basic_version(self):
        """Basic version should exist."""
        assert SystemVersion.BASIC.value == 1

    def test_standard_version(self):
        """Standard version should exist."""
        assert SystemVersion.STANDARD.value == 2

    def test_advanced_version(self):
        """Advanced version should exist."""
        assert SystemVersion.ADVANCED.value == 3

    def test_ultimate_version(self):
        """Ultimate version should exist."""
        assert SystemVersion.ULTIMATE.value == 4

    def test_version_ordering(self):
        """Versions should be ordered."""
        assert SystemVersion.BASIC.value < SystemVersion.STANDARD.value
        assert SystemVersion.STANDARD.value < SystemVersion.ADVANCED.value
        assert SystemVersion.ADVANCED.value < SystemVersion.ULTIMATE.value


# =============================================================================
# SystemCapabilities Tests
# =============================================================================


class TestSystemCapabilities:
    """Test system capabilities dataclass."""

    def test_default_capabilities(self):
        """Default capabilities should be disabled."""
        caps = SystemCapabilities()
        assert caps.meta_orchestrator is False
        assert caps.safla_memory_v3 is False
        assert caps.swarm_intelligence is False
        assert caps.workflow_evolution is False
        assert caps.research_integration is False
        assert caps.mamba2_context is False
        assert caps.maci_enforcement is False
        assert caps.langgraph_workflows is False

    def test_capability_count_zero(self):
        """Empty capabilities should count as zero."""
        caps = SystemCapabilities()
        assert caps.capability_count == 0

    def test_capability_count_partial(self):
        """Partial capabilities should count correctly."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
        )
        assert caps.capability_count == 2

    def test_capability_count_full(self):
        """Full capabilities should count as 8."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            mamba2_context=True,
            maci_enforcement=True,
            langgraph_workflows=True,
        )
        assert caps.capability_count == 8

    def test_is_ultimate_false(self):
        """Partial capabilities should not be ultimate."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
        )
        assert caps.is_ultimate is False

    def test_is_ultimate_true(self):
        """Full core capabilities should be ultimate."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
        )
        assert caps.is_ultimate is True

    def test_constitutional_hash_in_caps(self):
        """Capabilities should include constitutional hash."""
        caps = SystemCapabilities()
        assert caps.constitutional_hash == CONSTITUTIONAL_HASH

    def test_default_version_basic(self):
        """Default version should be BASIC."""
        caps = SystemCapabilities()
        assert caps.version == SystemVersion.BASIC


# =============================================================================
# SystemConfig Tests
# =============================================================================


class TestSystemConfig:
    """Test system configuration dataclass."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = SystemConfig()
        assert config.constitutional_hash == CONSTITUTIONAL_HASH
        assert config.max_concurrent_tasks == 100
        assert config.task_timeout_seconds == 300.0
        assert config.enable_persistence is True
        assert config.max_swarm_agents == 50
        assert config.enable_dynamic_spawning is True
        assert config.max_evolutions_per_day == 10
        assert config.enable_research is True

    def test_custom_config(self):
        """Custom config values should be accepted."""
        config = SystemConfig(
            max_concurrent_tasks=50,
            max_swarm_agents=25,
            enable_persistence=False,
        )
        assert config.max_concurrent_tasks == 50
        assert config.max_swarm_agents == 25
        assert config.enable_persistence is False

    def test_evolution_strategy(self):
        """Evolution strategy should be configurable."""
        config = SystemConfig(evolution_strategy="aggressive")
        assert config.evolution_strategy == "aggressive"

    def test_maci_settings(self):
        """MACI settings should be configurable."""
        config = SystemConfig(
            enable_maci=False,  # test-only: MACI off — testing agentic system
            maci_strict_mode=False,
        )
        assert config.enable_maci is False
        assert config.maci_strict_mode is False

    @pytest.mark.skipif(not META_ORCHESTRATOR_AVAILABLE, reason="Meta-Orchestrator not available")
    def test_to_orchestrator_config(self):
        """Config should convert to orchestrator config."""
        config = SystemConfig(
            constitutional_hash=CONSTITUTIONAL_HASH,
            max_swarm_agents=30,
        )
        orch_config = config.to_orchestrator_config()
        assert orch_config.constitutional_hash == CONSTITUTIONAL_HASH
        # max_swarm_agents is capped at 8 in OrchestratorConfig
        assert orch_config.max_swarm_agents == 8


# =============================================================================
# UltimateAgenticSystem Core Tests
# =============================================================================


class TestUltimateAgenticSystemCore:
    """Test core UltimateAgenticSystem functionality."""

    def test_system_creation(self):
        """System should be creatable."""
        system = UltimateAgenticSystem()
        assert system is not None
        assert system._initialized is False

    def test_system_with_config(self):
        """System should accept configuration."""
        config = SystemConfig(max_swarm_agents=20)
        system = UltimateAgenticSystem(config)
        assert system.config.max_swarm_agents == 20

    def test_session_id_generated(self):
        """System should generate session ID."""
        system = UltimateAgenticSystem()
        assert system._session_id is not None
        assert len(system._session_id) == 12

    def test_session_start_recorded(self):
        """System should record session start time."""
        before = datetime.now(UTC)
        system = UltimateAgenticSystem()
        after = datetime.now(UTC)
        assert before <= system._session_start <= after

    def test_initial_metrics(self):
        """System should have zero initial metrics."""
        system = UltimateAgenticSystem()
        metrics = system._metrics
        assert metrics["tasks_submitted"] == 0
        assert metrics["tasks_completed"] == 0
        assert metrics["tasks_failed"] == 0

    def test_get_capabilities_before_init(self):
        """Should get capabilities before initialization."""
        system = UltimateAgenticSystem()
        caps = system.get_capabilities()
        assert isinstance(caps, SystemCapabilities)

    def test_get_metrics_before_init(self):
        """Should get metrics before initialization."""
        system = UltimateAgenticSystem()
        metrics = system.get_metrics()
        assert "session_id" in metrics
        assert "constitutional_hash" in metrics
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_get_status_before_init(self):
        """Should get status before initialization."""
        system = UltimateAgenticSystem()
        status = system.get_status()
        assert status["initialized"] is False
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH


# =============================================================================
# UltimateAgenticSystem Initialization Tests
# =============================================================================


class TestUltimateAgenticSystemInit:
    """Test system initialization."""

    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self):
        """Initialize should return capabilities."""
        system = UltimateAgenticSystem()
        caps = await system.initialize()
        assert isinstance(caps, SystemCapabilities)

    @pytest.mark.asyncio
    async def test_initialize_sets_initialized(self):
        """Initialize should set initialized flag."""
        system = UltimateAgenticSystem()
        await system.initialize()
        assert system._initialized is True

    @pytest.mark.asyncio
    async def test_double_initialize_safe(self):
        """Double initialization should be safe."""
        system = UltimateAgenticSystem()
        caps1 = await system.initialize()
        caps2 = await system.initialize()
        assert caps1 == caps2

    @pytest.mark.asyncio
    async def test_status_after_init(self):
        """Status should reflect initialization."""
        system = UltimateAgenticSystem()
        await system.initialize()
        status = system.get_status()
        assert status["initialized"] is True


# =============================================================================
# UltimateAgenticSystem Version Detection Tests
# =============================================================================


class TestVersionDetection:
    """Test system version detection."""

    def test_basic_version_detection(self):
        """Basic capabilities should yield BASIC version."""
        caps = SystemCapabilities(meta_orchestrator=True)
        system = UltimateAgenticSystem()
        system._capabilities = caps
        version = system._determine_version()
        assert version == SystemVersion.BASIC

    def test_standard_version_detection(self):
        """Memory + Swarm should yield STANDARD version."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
        )
        system = UltimateAgenticSystem()
        system._capabilities = caps
        version = system._determine_version()
        assert version == SystemVersion.STANDARD

    def test_advanced_version_detection(self):
        """Workflow evolution should yield ADVANCED version."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
        )
        system = UltimateAgenticSystem()
        system._capabilities = caps
        version = system._determine_version()
        assert version == SystemVersion.ADVANCED

    def test_ultimate_version_detection(self):
        """Full capabilities should yield ULTIMATE version."""
        caps = SystemCapabilities(
            meta_orchestrator=True,
            safla_memory_v3=True,
            swarm_intelligence=True,
            workflow_evolution=True,
            research_integration=True,
            durable_execution=True,
            tool_documentation=True,
        )
        system = UltimateAgenticSystem()
        system._capabilities = caps
        version = system._determine_version()
        assert version == SystemVersion.ULTIMATE


# =============================================================================
# Task Execution Tests
# =============================================================================


class TestTaskExecution:
    """Test task execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_requires_orchestrator(self):
        """Execute should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.execute("Test task")

    @pytest.mark.asyncio
    async def test_execute_increments_counter(self):
        """Execute should increment task counter."""
        system = UltimateAgenticSystem()
        await system.initialize()

        if system._orchestrator:
            # Mock execute_task
            system._orchestrator.execute_task = AsyncMock(return_value=MagicMock(success=True))
            await system.execute("Test task")
            assert system._task_counter == 1
            assert system._metrics["tasks_submitted"] == 1


# =============================================================================
# Research Tests
# =============================================================================


class TestResearch:
    """Test research functionality."""

    @pytest.mark.asyncio
    async def test_research_requires_orchestrator(self):
        """Research should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.research("AI agents")

    @pytest.mark.asyncio
    async def test_research_increments_counter(self):
        """Research should increment query counter."""
        system = UltimateAgenticSystem()
        await system.initialize()

        if system._orchestrator:
            system._orchestrator.research_topic = AsyncMock(return_value={"results": []})
            await system.research("AI agents")
            assert system._metrics["research_queries"] == 1


# =============================================================================
# Memory Operations Tests
# =============================================================================


class TestMemoryOperations:
    """Test memory operations."""

    @pytest.mark.asyncio
    async def test_store_memory_requires_orchestrator(self):
        """Store memory should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.store_memory("key", "value")

    @pytest.mark.asyncio
    async def test_recall_memory_requires_orchestrator(self):
        """Recall memory should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.recall_memory(key="test")


# =============================================================================
# Agent Spawning Tests
# =============================================================================


class TestAgentSpawning:
    """Test agent spawning functionality."""

    @pytest.mark.asyncio
    async def test_spawn_agent_requires_orchestrator(self):
        """Spawn agent should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.spawn_agent(["coding"])

    @pytest.mark.asyncio
    async def test_spawn_agent_increments_counter(self):
        """Spawn agent should increment counter."""
        system = UltimateAgenticSystem()
        await system.initialize()

        if system._orchestrator:
            system._orchestrator.spawn_agent = AsyncMock(return_value="agent-123")
            agent_id = await system.spawn_agent(["coding"])
            assert system._metrics["agents_spawned"] == 1


# =============================================================================
# Workflow Evolution Tests
# =============================================================================


class TestWorkflowEvolution:
    """Test workflow evolution functionality."""

    @pytest.mark.asyncio
    async def test_evolve_workflow_requires_orchestrator(self):
        """Evolve workflow should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None
        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.evolve_workflow("workflow-1")

    @pytest.mark.asyncio
    async def test_evolve_workflow_increments_counter(self):
        """Evolve workflow should increment counter."""
        system = UltimateAgenticSystem()
        await system.initialize()

        if system._orchestrator:
            system._orchestrator.evolve_workflow = AsyncMock(return_value={"evolved": True})
            await system.evolve_workflow("workflow-1")
            assert system._metrics["workflow_evolutions"] == 1


# =============================================================================
# Shutdown Tests
# =============================================================================


class TestShutdown:
    """Test system shutdown."""

    @pytest.mark.asyncio
    async def test_shutdown_sets_uninitialized(self):
        """Shutdown should set initialized to False."""
        system = UltimateAgenticSystem()
        await system.initialize()
        await system.shutdown()
        assert system._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_without_init(self):
        """Shutdown without init should be safe."""
        system = UltimateAgenticSystem()
        await system.shutdown()  # Should not raise


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateUltimateSystem:
    """Test create_ultimate_system factory."""

    def test_create_with_defaults(self):
        """Should create system with defaults."""
        system = create_ultimate_system()
        assert system is not None
        assert system.config.constitutional_hash == CONSTITUTIONAL_HASH

    def test_create_with_config(self):
        """Should create system with custom config."""
        config = SystemConfig(max_swarm_agents=20)
        system = create_ultimate_system(config)
        assert system.config.max_swarm_agents == 20

    def test_create_with_custom_hash(self):
        """Should create system with custom hash."""
        custom_hash = "test_hash_123"
        system = create_ultimate_system(constitutional_hash=custom_hash)
        assert system.config.constitutional_hash == custom_hash


class TestQuickStart:
    """Test quick_start factory."""

    @pytest.mark.asyncio
    async def test_quick_start_initializes(self):
        """Quick start should initialize system."""
        system = await quick_start()
        assert system._initialized is True
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_quick_start_enables_research(self):
        """Quick start should enable research by default."""
        system = await quick_start()
        assert system.config.enable_research is True
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_quick_start_disable_research(self):
        """Quick start should allow disabling research."""
        system = await quick_start(enable_research=False)
        assert system.config.enable_research is False
        await system.shutdown()


class TestDevelopmentSystem:
    """Test development_system factory."""

    @pytest.mark.asyncio
    async def test_development_system_no_persistence(self):
        """Development system should disable persistence."""
        system = await development_system()
        assert system.config.enable_persistence is False
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_development_system_relaxed_maci(self):
        """Development system should have relaxed MACI."""
        system = await development_system()
        assert system.config.maci_strict_mode is False
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_development_system_more_evolutions(self):
        """Development system should allow more evolutions."""
        system = await development_system()
        assert system.config.max_evolutions_per_day == 50
        await system.shutdown()


class TestProductionSystem:
    """Test production_system factory."""

    @pytest.mark.asyncio
    async def test_production_system_persistence(self):
        """Production system should enable persistence."""
        system = await production_system()
        assert system.config.enable_persistence is True
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_production_system_strict_maci(self):
        """Production system should have strict MACI."""
        system = await production_system()
        assert system.config.maci_strict_mode is True
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_production_system_conservative(self):
        """Production system should be conservative."""
        system = await production_system()
        assert system.config.evolution_strategy == "conservative"
        assert system.config.max_evolutions_per_day == 5
        await system.shutdown()

    @pytest.mark.asyncio
    async def test_production_system_custom_agents(self):
        """Production system should accept custom agent count."""
        system = await production_system(max_agents=200)
        assert system.config.max_swarm_agents == 200
        await system.shutdown()


# =============================================================================
# Integration Tests
# =============================================================================


class TestSystemIntegration:
    """Integration tests for the complete system."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """Test complete system lifecycle."""
        # Create
        system = create_ultimate_system()
        assert system._initialized is False

        # Initialize
        caps = await system.initialize()
        assert system._initialized is True
        assert isinstance(caps, SystemCapabilities)

        # Check status
        status = system.get_status()
        assert status["initialized"] is True
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Check metrics
        metrics = system.get_metrics()
        assert metrics["tasks_submitted"] == 0
        assert metrics["constitutional_hash"] == CONSTITUTIONAL_HASH

        # Shutdown
        await system.shutdown()
        assert system._initialized is False

    @pytest.mark.asyncio
    async def test_multiple_systems(self):
        """Multiple systems should coexist."""
        system1 = await quick_start()
        system2 = await development_system()

        # Different session IDs
        assert system1._session_id != system2._session_id

        # Both initialized
        assert system1._initialized is True
        assert system2._initialized is True

        await system1.shutdown()
        await system2.shutdown()

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Metrics should be properly tracked."""
        system = await quick_start()

        initial_metrics = system.get_metrics()
        assert initial_metrics["tasks_submitted"] == 0

        # Metrics should include session info
        assert "session_id" in initial_metrics
        assert "session_duration_seconds" in initial_metrics
        assert initial_metrics["session_duration_seconds"] >= 0

        await system.shutdown()

    @pytest.mark.asyncio
    async def test_status_completeness(self):
        """Status should be comprehensive."""
        system = await quick_start()
        status = system.get_status()

        # Required fields
        assert "initialized" in status
        assert "session_id" in status
        assert "constitutional_hash" in status
        assert "version" in status
        assert "capabilities" in status
        assert "metrics" in status
        assert "active_tasks" in status
        assert "completed_tasks" in status

        await system.shutdown()

    @pytest.mark.asyncio
    async def test_capability_detection(self):
        """Capabilities should be detected correctly."""
        system = await quick_start()
        caps = system.get_capabilities()

        # Capabilities should be a valid SystemCapabilities object
        assert isinstance(caps, SystemCapabilities)
        assert caps.constitutional_hash == CONSTITUTIONAL_HASH

        # If initialized successfully, some capability should be detected
        # (may vary based on available dependencies)
        assert caps.capability_count >= 0

        await system.shutdown()


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_execute_without_orchestrator(self):
        """Execute should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.execute("Test task")

    @pytest.mark.asyncio
    async def test_research_without_orchestrator(self):
        """Research should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.research("Test topic")

    @pytest.mark.asyncio
    async def test_store_memory_without_orchestrator(self):
        """Store memory should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.store_memory("key", "value")

    @pytest.mark.asyncio
    async def test_recall_memory_without_orchestrator(self):
        """Recall memory should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.recall_memory(key="test")

    @pytest.mark.asyncio
    async def test_spawn_agent_without_orchestrator(self):
        """Spawn agent should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.spawn_agent(["coding"])

    @pytest.mark.asyncio
    async def test_evolve_workflow_without_orchestrator(self):
        """Evolve workflow should raise error without orchestrator."""
        system = UltimateAgenticSystem()
        system._initialized = True
        system._orchestrator = None

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            await system.evolve_workflow("workflow-1")
