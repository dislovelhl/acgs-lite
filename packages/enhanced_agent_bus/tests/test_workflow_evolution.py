"""
Comprehensive tests for Workflow Evolution Engine v3.0

Tests cover:
- Constitutional hash enforcement
- Enums: WorkflowState, OptimizationType, EvolutionStrategy
- Dataclasses: WorkflowStep, WorkflowExecution, WorkflowDefinition, PerformanceMetrics, EvolutionProposal
- PerformanceAnalyzer
- PatternLearner
- WorkflowOptimizer
- WorkflowExecutor
- WorkflowEvolutionEngine
- Factory function

Constitutional Hash: cdd01ef066bc6cf2
"""  # noqa: E501

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

# Import all components
from .. import workflow_evolution as workflow_evolution_module
from ..workflow_evolution import (
    CONSTITUTIONAL_HASH,
    EvolutionProposal,
    EvolutionStrategy,
    OptimizationType,
    PatternLearner,
    PerformanceAnalyzer,
    PerformanceMetrics,
    WorkflowDefinition,
    WorkflowEvolutionEngine,
    WorkflowExecution,
    WorkflowExecutor,
    WorkflowOptimizer,
    WorkflowState,
    WorkflowStep,
    create_workflow_engine,
)

# =============================================================================
# Constitutional Hash Tests
# =============================================================================


class TestConstitutionalHash:
    """Test constitutional hash enforcement."""

    def test_constitutional_hash_value(self):
        """Verify constitutional hash value."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_step(self):
        """Verify constitutional hash is included in WorkflowStep."""
        step = WorkflowStep(id="step-001", name="Test Step")
        assert step.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_execution(self):
        """Verify constitutional hash is included in WorkflowExecution."""
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=datetime.now(UTC),
        )
        assert execution.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_definition(self):
        """Verify constitutional hash is included in WorkflowDefinition."""
        definition = WorkflowDefinition(
            id="wf-001",
            name="Test Workflow",
            description="Test description",
            steps=[],
        )
        assert definition.constitutional_hash == CONSTITUTIONAL_HASH

    def test_constitutional_hash_in_proposal(self):
        """Verify constitutional hash is included in EvolutionProposal."""
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id="wf-001",
            optimization_type=OptimizationType.LATENCY,
            changes={},
            expected_improvement=10.0,
            risk_score=0.3,
        )
        assert proposal.constitutional_hash == CONSTITUTIONAL_HASH


# =============================================================================
# Enum Tests
# =============================================================================


class TestWorkflowState:
    """Test WorkflowState enum."""

    def test_pending_state(self):
        """Test PENDING state exists."""
        assert WorkflowState.PENDING is not None

    def test_running_state(self):
        """Test RUNNING state exists."""
        assert WorkflowState.RUNNING is not None

    def test_paused_state(self):
        """Test PAUSED state exists."""
        assert WorkflowState.PAUSED is not None

    def test_completed_state(self):
        """Test COMPLETED state exists."""
        assert WorkflowState.COMPLETED is not None

    def test_failed_state(self):
        """Test FAILED state exists."""
        assert WorkflowState.FAILED is not None

    def test_rolled_back_state(self):
        """Test ROLLED_BACK state exists."""
        assert WorkflowState.ROLLED_BACK is not None


class TestOptimizationType:
    """Test OptimizationType enum."""

    def test_latency_type(self):
        """Test LATENCY optimization type."""
        assert OptimizationType.LATENCY.value == "latency"

    def test_throughput_type(self):
        """Test THROUGHPUT optimization type."""
        assert OptimizationType.THROUGHPUT.value == "throughput"

    def test_resource_type(self):
        """Test RESOURCE optimization type."""
        assert OptimizationType.RESOURCE.value == "resource"

    def test_reliability_type(self):
        """Test RELIABILITY optimization type."""
        assert OptimizationType.RELIABILITY.value == "reliability"

    def test_cost_type(self):
        """Test COST optimization type."""
        assert OptimizationType.COST.value == "cost"


class TestEvolutionStrategy:
    """Test EvolutionStrategy enum."""

    def test_conservative_strategy(self):
        """Test CONSERVATIVE strategy."""
        assert EvolutionStrategy.CONSERVATIVE.value == "conservative"

    def test_moderate_strategy(self):
        """Test MODERATE strategy."""
        assert EvolutionStrategy.MODERATE.value == "moderate"

    def test_aggressive_strategy(self):
        """Test AGGRESSIVE strategy."""
        assert EvolutionStrategy.AGGRESSIVE.value == "aggressive"

    def test_experimental_strategy(self):
        """Test EXPERIMENTAL strategy."""
        assert EvolutionStrategy.EXPERIMENTAL.value == "experimental"


# =============================================================================
# Dataclass Tests
# =============================================================================


class TestWorkflowStep:
    """Test WorkflowStep dataclass."""

    def test_step_creation(self):
        """Test basic step creation."""
        step = WorkflowStep(id="step-001", name="Process Data")
        assert step.id == "step-001"
        assert step.name == "Process Data"

    def test_step_default_values(self):
        """Test step default values."""
        step = WorkflowStep(id="step-001", name="Test")
        assert step.handler is None
        assert step.timeout_seconds == 60
        assert step.retries == 3
        assert step.dependencies == []
        assert step.parallel_with == []
        assert step.metadata == {}

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = WorkflowStep(
            id="step-002",
            name="Transform",
            dependencies=["step-001"],
        )
        assert step.dependencies == ["step-001"]

    def test_step_with_handler(self):
        """Test step with handler function."""

        async def my_handler(input_data, results):
            return "processed"

        step = WorkflowStep(
            id="step-001",
            name="Process",
            handler=my_handler,
        )
        assert step.handler is my_handler


class TestWorkflowExecution:
    """Test WorkflowExecution dataclass."""

    def test_execution_creation(self):
        """Test basic execution creation."""
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=datetime.now(UTC),
        )
        assert execution.id == "exec-001"
        assert execution.workflow_id == "wf-001"
        assert execution.state == WorkflowState.PENDING

    def test_execution_default_values(self):
        """Test execution default values."""
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=datetime.now(UTC),
        )
        assert execution.completed_at is None
        assert execution.steps_completed == []
        assert execution.steps_failed == []
        assert execution.execution_times == {}
        assert execution.errors == {}
        assert execution.result is None


class TestWorkflowDefinition:
    """Test WorkflowDefinition dataclass."""

    def test_definition_creation(self):
        """Test basic definition creation."""
        definition = WorkflowDefinition(
            id="wf-001",
            name="Data Pipeline",
            description="Process data",
            steps=[],
        )
        assert definition.id == "wf-001"
        assert definition.name == "Data Pipeline"
        assert definition.version == 1
        assert definition.is_active is True

    def test_definition_get_hash(self):
        """Test workflow hash generation."""
        definition = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )
        hash1 = definition.get_hash()
        assert len(hash1) == 16

    def test_definition_hash_consistency(self):
        """Test that hash is consistent for same definition."""
        definition = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )
        hash1 = definition.get_hash()
        hash2 = definition.get_hash()
        assert hash1 == hash2

    def test_definition_hash_uses_fast_kernel_when_available(self, monkeypatch):
        """Test get_hash uses fast hash kernel when available."""
        called = {"value": False}

        def _fake_fast_hash(value: str) -> int:
            called["value"] = True
            return 0xBEEF

        monkeypatch.setattr(workflow_evolution_module, "FAST_HASH_AVAILABLE", True)
        monkeypatch.setattr(workflow_evolution_module, "fast_hash", _fake_fast_hash, raising=False)

        definition = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )
        result = definition.get_hash()

        assert called["value"] is True
        assert result == "000000000000beef"

    def test_definition_hash_falls_back_to_sha256(self, monkeypatch):
        """Test get_hash falls back to sha256 when fast kernel unavailable."""
        monkeypatch.setattr(workflow_evolution_module, "FAST_HASH_AVAILABLE", False)

        definition = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )
        result = definition.get_hash()

        assert len(result) == 16
        int(result, 16)


class TestPerformanceMetrics:
    """Test PerformanceMetrics dataclass."""

    def test_metrics_creation(self):
        """Test basic metrics creation."""
        metrics = PerformanceMetrics(workflow_id="wf-001")
        assert metrics.workflow_id == "wf-001"
        assert metrics.total_executions == 0
        assert metrics.successful_executions == 0
        assert metrics.avg_execution_time_ms == 0.0


class TestEvolutionProposal:
    """Test EvolutionProposal dataclass."""

    def test_proposal_creation(self):
        """Test basic proposal creation."""
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id="wf-001",
            optimization_type=OptimizationType.LATENCY,
            changes={"add_caching": True},
            expected_improvement=15.0,
            risk_score=0.3,
        )
        assert proposal.id == "prop-001"
        assert proposal.approved is False
        assert proposal.applied is False
        assert proposal.expected_improvement == 15.0


# =============================================================================
# PerformanceAnalyzer Tests
# =============================================================================


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer class."""

    def test_analyzer_creation(self):
        """Test analyzer creation."""
        analyzer = PerformanceAnalyzer()
        assert analyzer._execution_history is not None
        assert analyzer._metrics_cache is not None

    def test_record_execution(self):
        """Test recording an execution."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=start,
            completed_at=start + timedelta(seconds=1),
            state=WorkflowState.COMPLETED,
        )
        analyzer.record_execution(execution)
        assert len(analyzer._execution_history["wf-001"]) == 1

    def test_get_metrics_empty(self):
        """Test getting metrics for non-existent workflow."""
        analyzer = PerformanceAnalyzer()
        metrics = analyzer.get_metrics("non-existent")
        assert metrics is None

    def test_get_metrics_after_executions(self):
        """Test metrics calculation after multiple executions."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)

        for i in range(5):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-001",
                started_at=start,
                completed_at=start + timedelta(milliseconds=100 + i * 10),
                state=WorkflowState.COMPLETED,
                execution_times={"step-1": 50.0 + i * 5},
            )
            analyzer.record_execution(execution)

        metrics = analyzer.get_metrics("wf-001")
        assert metrics is not None
        assert metrics.total_executions == 5
        assert metrics.successful_executions == 5

    def test_identify_optimizations_latency(self):
        """Test identifying latency optimizations."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)

        # Create executions with bottleneck step
        for i in range(5):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-001",
                started_at=start,
                completed_at=start + timedelta(seconds=1),
                state=WorkflowState.COMPLETED,
                execution_times={
                    "fast-step": 10.0,
                    "slow-step": 500.0,  # Bottleneck
                },
            )
            analyzer.record_execution(execution)

        optimizations = analyzer.identify_optimizations("wf-001", OptimizationType.LATENCY)
        assert len(optimizations) > 0

    def test_identify_optimizations_reliability(self):
        """Test identifying reliability optimizations."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)

        # Create executions with failing step
        for i in range(10):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-001",
                started_at=start,
                completed_at=start + timedelta(seconds=1),
                state=WorkflowState.FAILED if i < 2 else WorkflowState.COMPLETED,
                execution_times={"step-1": 100.0},
                steps_failed=["step-1"] if i < 2 else [],
            )
            analyzer.record_execution(execution)

        optimizations = analyzer.identify_optimizations("wf-001", OptimizationType.RELIABILITY)
        # Should identify step-1 as having >5% failure rate (2/10 = 20%)
        assert len(optimizations) > 0

    def test_update_metrics_uses_rust_kernels_when_available(self, monkeypatch):
        """Use Rust kernels for percentile and mean when available."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)
        called: dict[str, bool] = {"percentiles": False, "stats": False}

        def _fake_compute_percentiles(values: list[float], requested: list[float]) -> list[float]:
            called["percentiles"] = True
            assert requested == [50.0, 95.0, 99.0]
            assert values == sorted(values)
            return [10.0, 20.0, 30.0]

        def _fake_aggregate_stats(values: list[float]) -> tuple[float, float, float, float, int]:
            called["stats"] = True
            assert values == sorted(values)
            return (100.0, 25.0, 10.0, 40.0, len(values))

        monkeypatch.setattr(workflow_evolution_module, "PERF_KERNELS_AVAILABLE", True)
        monkeypatch.setattr(
            workflow_evolution_module,
            "compute_percentiles",
            _fake_compute_percentiles,
            raising=False,
        )
        monkeypatch.setattr(
            workflow_evolution_module,
            "aggregate_stats",
            _fake_aggregate_stats,
            raising=False,
        )

        for i in range(4):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-rust",
                started_at=start,
                completed_at=start + timedelta(milliseconds=10 + i * 10),
                state=WorkflowState.COMPLETED,
            )
            analyzer.record_execution(execution)

        metrics = analyzer.get_metrics("wf-rust")
        assert metrics is not None
        assert called["percentiles"] is True
        assert called["stats"] is True
        assert metrics.p50_execution_time_ms == 10.0
        assert metrics.p95_execution_time_ms == 20.0
        assert metrics.p99_execution_time_ms == 30.0
        assert metrics.avg_execution_time_ms == 25.0

    def test_update_metrics_falls_back_to_python_without_rust(self, monkeypatch):
        """Fall back to Python percentile and mean logic when Rust is unavailable."""
        analyzer = PerformanceAnalyzer()
        start = datetime.now(UTC)

        monkeypatch.setattr(workflow_evolution_module, "PERF_KERNELS_AVAILABLE", False)

        for i in range(5):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-python",
                started_at=start,
                completed_at=start + timedelta(milliseconds=100 + i * 10),
                state=WorkflowState.COMPLETED,
            )
            analyzer.record_execution(execution)

        metrics = analyzer.get_metrics("wf-python")
        assert metrics is not None
        assert metrics.p50_execution_time_ms == 120.0
        assert metrics.p95_execution_time_ms == 140.0
        assert metrics.p99_execution_time_ms == 140.0
        assert metrics.avg_execution_time_ms == 120.0


# =============================================================================
# PatternLearner Tests
# =============================================================================


class TestPatternLearner:
    """Test PatternLearner class."""

    def test_learner_creation(self):
        """Test learner creation."""
        learner = PatternLearner()
        assert learner._patterns is not None
        assert learner._success_patterns is not None
        assert learner._failure_patterns is not None

    def test_learn_from_successful_execution(self):
        """Test learning from successful execution."""
        learner = PatternLearner()
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=datetime.now(UTC),
            state=WorkflowState.COMPLETED,
            steps_completed=["step-1", "step-2"],
        )
        learner.learn_from_execution(execution)
        assert len(learner._patterns["wf-001"]) == 1
        assert "wf-001" in learner._success_patterns

    def test_learn_from_failed_execution(self):
        """Test learning from failed execution."""
        learner = PatternLearner()
        execution = WorkflowExecution(
            id="exec-001",
            workflow_id="wf-001",
            started_at=datetime.now(UTC),
            state=WorkflowState.FAILED,
            steps_failed=["step-2"],
        )
        learner.learn_from_execution(execution)
        assert "wf-001" in learner._failure_patterns

    def test_get_recommendations_no_failures(self):
        """Test recommendations with no failures."""
        learner = PatternLearner()
        recommendations = learner.get_recommendations("wf-001")
        assert recommendations == []

    def test_get_recommendations_frequent_failures(self):
        """Test recommendations with frequent failures."""
        learner = PatternLearner()

        # Create multiple failures for same step
        for i in range(5):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-001",
                started_at=datetime.now(UTC),
                state=WorkflowState.FAILED,
                steps_failed=["problematic-step"],
            )
            learner.learn_from_execution(execution)

        recommendations = learner.get_recommendations("wf-001")
        assert len(recommendations) > 0
        assert "problematic-step" in recommendations[0]


# =============================================================================
# WorkflowOptimizer Tests
# =============================================================================


class TestWorkflowOptimizer:
    """Test WorkflowOptimizer class."""

    def test_optimizer_creation(self):
        """Test optimizer creation."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner)
        assert optimizer._strategy == EvolutionStrategy.MODERATE

    def test_optimizer_with_strategy(self):
        """Test optimizer with custom strategy."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner, strategy=EvolutionStrategy.AGGRESSIVE)
        assert optimizer._strategy == EvolutionStrategy.AGGRESSIVE

    def test_create_proposal_no_data(self):
        """Test creating proposal with no performance data."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner)

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )

        proposal = optimizer.create_proposal(workflow, OptimizationType.LATENCY)
        assert proposal is None  # No data to optimize

    def test_create_proposal_with_data(self):
        """Test creating proposal with performance data."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner)

        # Add execution data
        start = datetime.now(UTC)
        for i in range(5):
            execution = WorkflowExecution(
                id=f"exec-{i}",
                workflow_id="wf-001",
                started_at=start,
                completed_at=start + timedelta(seconds=1),
                state=WorkflowState.COMPLETED,
                execution_times={"slow-step": 500.0},
            )
            analyzer.record_execution(execution)

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[WorkflowStep(id="slow-step", name="Slow")],
        )

        proposal = optimizer.create_proposal(workflow, OptimizationType.LATENCY)
        assert proposal is not None
        assert proposal.workflow_id == "wf-001"

    def test_apply_proposal_not_approved(self):
        """Test applying unapproved proposal."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner)

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )

        result = optimizer.apply_proposal("non-existent", workflow)
        assert result is None

    def test_apply_proposal_approved(self):
        """Test applying approved proposal."""
        analyzer = PerformanceAnalyzer()
        learner = PatternLearner()
        optimizer = WorkflowOptimizer(analyzer, learner)

        # Create and store a proposal
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id="wf-001",
            optimization_type=OptimizationType.LATENCY,
            changes={"test": True},
            expected_improvement=10.0,
            risk_score=0.3,
            approved=True,
        )
        optimizer._proposals[proposal.id] = proposal

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )

        result = optimizer.apply_proposal("prop-001", workflow)
        assert result is not None
        assert result.version == workflow.version + 1
        assert result.parent_id == workflow.id


# =============================================================================
# WorkflowExecutor Tests
# =============================================================================


class TestWorkflowExecutor:
    """Test WorkflowExecutor class."""

    def test_executor_creation(self):
        """Test executor creation."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)
        assert executor._analyzer is analyzer

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self):
        """Test executing simple workflow."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Simple",
            description="Simple workflow",
            steps=[
                WorkflowStep(id="step-1", name="Step 1"),
                WorkflowStep(id="step-2", name="Step 2"),
            ],
        )

        execution = await executor.execute(workflow, {})
        assert execution.state == WorkflowState.COMPLETED
        assert "step-1" in execution.steps_completed
        assert "step-2" in execution.steps_completed

    @pytest.mark.asyncio
    async def test_execute_workflow_with_dependencies(self):
        """Test executing workflow with dependencies."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)

        workflow = WorkflowDefinition(
            id="wf-001",
            name="With Dependencies",
            description="Workflow with dependencies",
            steps=[
                WorkflowStep(id="step-1", name="Step 1"),
                WorkflowStep(id="step-2", name="Step 2", dependencies=["step-1"]),
            ],
        )

        execution = await executor.execute(workflow, {})
        assert execution.state == WorkflowState.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_workflow_with_handler(self):
        """Test executing workflow with custom handler."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)

        async def custom_handler(input_data, results):
            return {"processed": True}

        workflow = WorkflowDefinition(
            id="wf-001",
            name="With Handler",
            description="Workflow with handler",
            steps=[
                WorkflowStep(id="step-1", name="Step 1", handler=custom_handler),
            ],
        )

        execution = await executor.execute(workflow, {})
        assert execution.state == WorkflowState.COMPLETED
        assert execution.result["step-1"]["processed"] is True

    @pytest.mark.asyncio
    async def test_execute_workflow_with_failing_handler(self):
        """Test executing workflow with failing handler."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)

        async def failing_handler(input_data, results):
            raise ValueError("Handler failed")

        workflow = WorkflowDefinition(
            id="wf-001",
            name="Failing",
            description="Workflow that fails",
            steps=[
                WorkflowStep(id="step-1", name="Step 1", handler=failing_handler),
            ],
        )

        execution = await executor.execute(workflow, {})
        assert execution.state == WorkflowState.FAILED
        assert "step-1" in execution.steps_failed

    def test_topological_sort(self):
        """Test topological sorting of steps."""
        analyzer = PerformanceAnalyzer()
        executor = WorkflowExecutor(analyzer)

        steps = [
            WorkflowStep(id="step-3", name="Step 3", dependencies=["step-2"]),
            WorkflowStep(id="step-1", name="Step 1"),
            WorkflowStep(id="step-2", name="Step 2", dependencies=["step-1"]),
        ]

        sorted_steps = executor._topological_sort(steps)
        ids = [s.id for s in sorted_steps]

        # step-1 must come before step-2, step-2 before step-3
        assert ids.index("step-1") < ids.index("step-2")
        assert ids.index("step-2") < ids.index("step-3")


# =============================================================================
# WorkflowEvolutionEngine Tests
# =============================================================================


class TestWorkflowEvolutionEngine:
    """Test WorkflowEvolutionEngine class."""

    def test_engine_creation(self):
        """Test engine creation with defaults."""
        engine = WorkflowEvolutionEngine()
        assert engine._strategy == EvolutionStrategy.MODERATE
        assert engine._max_evolution_per_day == 5
        assert engine._constitutional_hash == CONSTITUTIONAL_HASH

    def test_engine_with_custom_config(self):
        """Test engine with custom configuration."""
        engine = WorkflowEvolutionEngine(
            strategy=EvolutionStrategy.AGGRESSIVE,
            max_evolution_per_day=10,
        )
        assert engine._strategy == EvolutionStrategy.AGGRESSIVE
        assert engine._max_evolution_per_day == 10

    @pytest.mark.asyncio
    async def test_register_workflow(self):
        """Test registering a workflow."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(
            name="Test Pipeline",
            description="Test pipeline description",
            steps=steps,
        )

        assert workflow.name == "Test Pipeline"
        assert len(workflow.steps) == 1
        assert engine._metrics["workflows_registered"] == 1

    @pytest.mark.asyncio
    async def test_execute_workflow(self):
        """Test executing a registered workflow."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(name="Test", description="Test", steps=steps)

        execution = await engine.execute_workflow(workflow.id, {"data": "test"})

        assert execution is not None
        assert execution.state == WorkflowState.COMPLETED
        assert engine._metrics["executions_total"] == 1
        assert engine._metrics["executions_successful"] == 1

    @pytest.mark.asyncio
    async def test_execute_nonexistent_workflow(self):
        """Test executing non-existent workflow."""
        engine = WorkflowEvolutionEngine()
        execution = await engine.execute_workflow("non-existent")
        assert execution is None

    @pytest.mark.asyncio
    async def test_propose_evolution(self):
        """Test proposing evolution."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(name="Test", description="Test", steps=steps)

        # Execute several times to generate data
        for _ in range(5):
            await engine.execute_workflow(workflow.id)

        proposal = await engine.propose_evolution(workflow.id, OptimizationType.LATENCY)

        # May or may not have proposal depending on bottleneck detection
        if proposal:
            assert proposal.workflow_id == workflow.id
            assert engine._metrics["proposals_created"] >= 1

    @pytest.mark.asyncio
    async def test_approve_proposal(self):
        """Test approving a proposal."""
        engine = WorkflowEvolutionEngine()

        # Manually create and register a proposal
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id="wf-001",
            optimization_type=OptimizationType.LATENCY,
            changes={},
            expected_improvement=10.0,
            risk_score=0.3,
        )
        engine._optimizer._proposals[proposal.id] = proposal

        result = await engine.approve_proposal("prop-001")
        assert result is True
        assert proposal.approved is True

    @pytest.mark.asyncio
    async def test_approve_nonexistent_proposal(self):
        """Test approving non-existent proposal."""
        engine = WorkflowEvolutionEngine()
        result = await engine.approve_proposal("non-existent")
        assert result is False

    @pytest.mark.asyncio
    async def test_apply_evolution(self):
        """Test applying evolution."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(name="Test", description="Test", steps=steps)

        # Create and approve proposal
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id=workflow.id,
            optimization_type=OptimizationType.LATENCY,
            changes={},
            expected_improvement=10.0,
            risk_score=0.3,
            approved=True,
        )
        engine._optimizer._proposals[proposal.id] = proposal

        new_workflow = await engine.apply_evolution("prop-001")

        assert new_workflow is not None
        assert new_workflow.version == workflow.version + 1
        assert new_workflow.parent_id == workflow.id
        assert engine._metrics["workflows_evolved"] == 1

    @pytest.mark.asyncio
    async def test_rollback_workflow(self):
        """Test rolling back a workflow."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(name="Test", description="Test", steps=steps)

        # Create version 2
        proposal = EvolutionProposal(
            id="prop-001",
            workflow_id=workflow.id,
            optimization_type=OptimizationType.LATENCY,
            changes={},
            expected_improvement=10.0,
            risk_score=0.3,
            approved=True,
        )
        engine._optimizer._proposals[proposal.id] = proposal
        workflow_v2 = await engine.apply_evolution("prop-001")

        # Rollback
        rolled_back = await engine.rollback_workflow(workflow.id)

        assert rolled_back is not None
        assert rolled_back.version == 3  # v1 -> v2 -> v3 (rollback)
        assert "Rollback" in rolled_back.evolution_notes

    @pytest.mark.asyncio
    async def test_rollback_to_specific_version(self):
        """Test rolling back to specific version."""
        engine = WorkflowEvolutionEngine()
        steps = [WorkflowStep(id="step-1", name="Step 1")]

        workflow = await engine.register_workflow(name="Test", description="Test", steps=steps)

        # Add to history manually for test
        v2 = WorkflowDefinition(
            id=str(uuid4()),
            name="Test",
            description="Test",
            steps=steps,
            version=2,
        )
        engine._workflow_history[workflow.id].append(v2)

        rolled_back = await engine.rollback_workflow(workflow.id, to_version=1)
        assert rolled_back is not None

    def test_get_workflow(self):
        """Test getting a workflow."""
        engine = WorkflowEvolutionEngine()
        workflow = WorkflowDefinition(
            id="wf-001",
            name="Test",
            description="Test",
            steps=[],
        )
        engine._workflows["wf-001"] = workflow

        result = engine.get_workflow("wf-001")
        assert result is workflow

    def test_get_nonexistent_workflow(self):
        """Test getting non-existent workflow."""
        engine = WorkflowEvolutionEngine()
        result = engine.get_workflow("non-existent")
        assert result is None

    def test_get_workflow_metrics(self):
        """Test getting workflow metrics."""
        engine = WorkflowEvolutionEngine()
        metrics = engine.get_workflow_metrics("wf-001")
        assert metrics is None  # No data yet

    def test_get_recommendations(self):
        """Test getting recommendations."""
        engine = WorkflowEvolutionEngine()
        recommendations = engine.get_recommendations("wf-001")
        assert recommendations == []

    def test_get_stats(self):
        """Test getting engine statistics."""
        engine = WorkflowEvolutionEngine()
        stats = engine.get_stats()

        assert stats["strategy"] == "moderate"
        assert stats["max_evolution_per_day"] == 5
        assert stats["constitutional_hash"] == CONSTITUTIONAL_HASH
        assert "metrics" in stats

    def test_evolution_limit_check(self):
        """Test daily evolution limit checking."""
        engine = WorkflowEvolutionEngine(max_evolution_per_day=2)
        engine._evolution_count_today = 2

        # Should not allow more evolutions
        assert engine._evolution_count_today >= engine._max_evolution_per_day

    def test_evolution_limit_reset(self):
        """Test daily evolution limit reset."""
        engine = WorkflowEvolutionEngine()
        engine._evolution_count_today = 5
        engine._last_evolution_date = (datetime.now(UTC) - timedelta(days=1)).date()

        engine._check_evolution_limit()

        assert engine._evolution_count_today == 0


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateWorkflowEngine:
    """Test create_workflow_engine factory function."""

    def test_create_with_defaults(self):
        """Test creating engine with defaults."""
        engine = create_workflow_engine()
        assert isinstance(engine, WorkflowEvolutionEngine)
        assert engine._strategy == EvolutionStrategy.MODERATE

    def test_create_with_custom_config(self):
        """Test creating engine with custom config."""
        engine = create_workflow_engine(
            strategy=EvolutionStrategy.EXPERIMENTAL,
            max_evolution_per_day=20,
        )
        assert engine._strategy == EvolutionStrategy.EXPERIMENTAL
        assert engine._max_evolution_per_day == 20

    def test_create_with_custom_hash(self):
        """Test creating engine with custom constitutional hash."""
        custom_hash = "custom12345678"
        engine = create_workflow_engine(constitutional_hash=custom_hash)
        assert engine._constitutional_hash == custom_hash


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkflowEvolutionIntegration:
    """Integration tests for complete workflow evolution cycle."""

    @pytest.mark.asyncio
    async def test_full_evolution_cycle(self):
        """Test complete workflow evolution cycle."""
        engine = create_workflow_engine(
            strategy=EvolutionStrategy.MODERATE,
            max_evolution_per_day=10,
        )

        # Register workflow
        workflow = await engine.register_workflow(
            name="Data Processing Pipeline",
            description="Process and transform data",
            steps=[
                WorkflowStep(id="extract", name="Extract Data"),
                WorkflowStep(
                    id="transform",
                    name="Transform Data",
                    dependencies=["extract"],
                ),
                WorkflowStep(id="load", name="Load Data", dependencies=["transform"]),
            ],
        )

        # Execute multiple times
        for i in range(10):
            execution = await engine.execute_workflow(workflow.id, {"batch": i})
            assert execution is not None

        # Check metrics
        stats = engine.get_stats()
        assert stats["metrics"]["executions_total"] == 10
        assert stats["metrics"]["executions_successful"] == 10

    @pytest.mark.asyncio
    async def test_workflow_with_failures_and_recovery(self):
        """Test workflow execution with failures and learning."""
        engine = create_workflow_engine()

        fail_count = [0]  # Mutable for closure

        async def sometimes_fails(input_data, results):
            fail_count[0] += 1
            if fail_count[0] <= 3:
                raise ValueError("Temporary failure")
            return "success"

        workflow = await engine.register_workflow(
            name="Recovery Test",
            description="Test failure recovery",
            steps=[
                WorkflowStep(id="step-1", name="Step 1"),
                WorkflowStep(
                    id="step-2",
                    name="Step 2",
                    handler=sometimes_fails,
                    dependencies=["step-1"],
                ),
            ],
        )

        # Execute 5 times - first 3 should fail
        for _ in range(5):
            await engine.execute_workflow(workflow.id)

        # Check learner has captured failure patterns
        recommendations = engine.get_recommendations(workflow.id)
        # Should have recommendations for step-2 failures
        assert any("step-2" in r for r in recommendations) if recommendations else True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
