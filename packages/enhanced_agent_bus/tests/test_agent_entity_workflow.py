"""
ACGS-2 Enhanced Agent Bus - Agent Entity Workflow Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for AgentEntityWorkflow and related components.
Tests cover: workflow lifecycle, signals, queries, activities, and error handling.
"""

import asyncio

import pytest

from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
from enhanced_agent_bus._compat.errors import (
    ConstitutionalViolationError as ACGSConstitutionalViolationError,
)
from enhanced_agent_bus._compat.errors import (
    ResourceNotFoundError as ACGSResourceNotFoundError,
)
from enhanced_agent_bus._compat.errors import (
    ServiceUnavailableError as ACGSServiceUnavailableError,
)
from enhanced_agent_bus._compat.errors import (
    ValidationError as ACGSValidationError,
)

# Import workflow components
from enhanced_agent_bus.workflows.agent_entity_workflow import (
    AgentConfig,
    AgentEntityWorkflow,
    AgentResult,
    AgentState,
    AgentStatus,
    CheckpointAgentActivity,
    ExecuteTaskActivity,
    InitializeAgentActivity,
    ShutdownAgentActivity,
    ShutdownRequest,
    Task,
    TaskPriority,
    TaskResult,
    WorkflowActivity,
    checkpoint_agent_activity,
    execute_task_activity,
    initialize_agent_activity,
    shutdown_agent_activity,
)
from enhanced_agent_bus.workflows.workflow_base import (
    InMemoryWorkflowExecutor,
    WorkflowContext,
    WorkflowStatus,
    query,
    signal,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def agent_config() -> AgentConfig:
    """Create a test agent configuration."""
    return AgentConfig(
        agent_id="test-agent-001",
        agent_type="worker",
        capabilities=["compute", "analyze"],
        max_concurrent_tasks=5,
        idle_timeout_seconds=10.0,  # Short for testing
        heartbeat_interval_seconds=1.0,
        checkpoint_interval_seconds=5.0,
        metadata={"environment": "test"},
    )


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task."""
    return Task(
        task_id="task-001",
        task_type="compute",
        payload={"data": "test-data"},
        priority=TaskPriority.NORMAL,
        timeout_seconds=5.0,
    )


@pytest.fixture
def workflow_context() -> WorkflowContext:
    """Create a test workflow context."""
    return WorkflowContext(
        workflow_id="wf-test-001",
        tenant_id="tenant-001",
    )


@pytest.fixture
def workflow_executor() -> InMemoryWorkflowExecutor:
    """Create an in-memory workflow executor."""
    return InMemoryWorkflowExecutor()


# =============================================================================
# Data Class Tests
# =============================================================================


class TestAgentConfig:
    """Tests for AgentConfig data class."""

    def test_default_values(self) -> None:
        """Test AgentConfig default values."""
        config = AgentConfig(agent_id="agent-1", agent_type="worker")
        assert config.agent_id == "agent-1"
        assert config.agent_type == "worker"
        assert config.capabilities == []
        assert config.max_concurrent_tasks == 5
        assert config.idle_timeout_seconds == 3600.0
        assert config.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def test_custom_values(self, agent_config: AgentConfig) -> None:
        """Test AgentConfig with custom values."""
        assert agent_config.agent_id == "test-agent-001"
        assert agent_config.agent_type == "worker"
        assert "compute" in agent_config.capabilities
        assert agent_config.metadata.get("environment") == "test"

    def test_to_dict(self, agent_config: AgentConfig) -> None:
        """Test AgentConfig serialization."""
        data = agent_config.to_dict()
        assert data["agent_id"] == "test-agent-001"
        assert data["agent_type"] == "worker"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret


class TestTask:
    """Tests for Task data class."""

    def test_default_values(self) -> None:
        """Test Task default values."""
        task = Task()
        assert task.task_id is not None
        assert task.task_type == ""
        assert task.priority == TaskPriority.NORMAL
        assert task.timeout_seconds == 300.0
        assert task.retry_count == 0
        assert task.max_retries == 3

    def test_custom_values(self, sample_task: Task) -> None:
        """Test Task with custom values."""
        assert sample_task.task_id == "task-001"
        assert sample_task.task_type == "compute"
        assert sample_task.payload["data"] == "test-data"

    def test_to_dict(self, sample_task: Task) -> None:
        """Test Task serialization."""
        data = sample_task.to_dict()
        assert data["task_id"] == "task-001"
        assert data["task_type"] == "compute"
        assert data["priority"] == TaskPriority.NORMAL.value


class TestTaskResult:
    """Tests for TaskResult data class."""

    def test_success_result(self) -> None:
        """Test successful task result."""
        result = TaskResult(
            task_id="task-001",
            success=True,
            result={"output": "completed"},
            duration_ms=100.0,
        )
        assert result.success is True
        assert result.result["output"] == "completed"
        assert result.error is None

    def test_failure_result(self) -> None:
        """Test failed task result."""
        result = TaskResult(
            task_id="task-001",
            success=False,
            error="Task timeout",
            duration_ms=5000.0,
        )
        assert result.success is False
        assert result.error == "Task timeout"
        assert result.result is None

    def test_to_dict(self) -> None:
        """Test TaskResult serialization."""
        result = TaskResult(task_id="task-001", success=True)
        data = result.to_dict()
        assert data["task_id"] == "task-001"
        assert data["success"] is True
        assert "constitutional_hash" in data


class TestAgentStatus:
    """Tests for AgentStatus data class."""

    def test_default_values(self) -> None:
        """Test AgentStatus default values."""
        status = AgentStatus(
            agent_id="agent-001",
            state=AgentState.IDLE,
        )
        assert status.agent_id == "agent-001"
        assert status.state == AgentState.IDLE
        assert status.tasks_completed == 0
        assert status.tasks_failed == 0

    def test_to_dict(self) -> None:
        """Test AgentStatus serialization."""
        status = AgentStatus(
            agent_id="agent-001",
            state=AgentState.PROCESSING,
            tasks_completed=5,
        )
        data = status.to_dict()
        assert data["agent_id"] == "agent-001"
        assert data["state"] == "processing"
        assert data["tasks_completed"] == 5


class TestAgentResult:
    """Tests for AgentResult data class."""

    def test_completed_result(self) -> None:
        """Test completed agent result."""
        result = AgentResult(
            agent_id="agent-001",
            final_state=AgentState.TERMINATED,
            total_tasks_completed=10,
            total_runtime_seconds=3600.0,
            shutdown_reason="idle_timeout",
        )
        assert result.agent_id == "agent-001"
        assert result.final_state == AgentState.TERMINATED
        assert result.total_tasks_completed == 10

    def test_to_dict(self) -> None:
        """Test AgentResult serialization."""
        result = AgentResult(
            agent_id="agent-001",
            final_state=AgentState.FAILED,
            shutdown_reason="error",
        )
        data = result.to_dict()
        assert data["agent_id"] == "agent-001"
        assert data["final_state"] == "failed"


# =============================================================================
# Workflow Base Tests
# =============================================================================


class TestWorkflowContext:
    """Tests for WorkflowContext."""

    def test_initialization(self, workflow_context: WorkflowContext) -> None:
        """Test WorkflowContext initialization."""
        assert workflow_context.workflow_id == "wf-test-001"
        assert workflow_context.tenant_id == "tenant-001"
        assert workflow_context.run_id is not None
        assert workflow_context.status == WorkflowStatus.PENDING

    def test_signal_queue(self, workflow_context: WorkflowContext) -> None:
        """Test signal queue creation."""
        queue = workflow_context.get_signal_queue("test_signal")
        assert queue is not None
        # Same signal returns same queue
        queue2 = workflow_context.get_signal_queue("test_signal")
        assert queue is queue2

    async def test_send_and_wait_for_signal(self, workflow_context: WorkflowContext) -> None:
        """Test signal send and receive."""

        # Send signal in background
        async def send_delayed():
            await asyncio.sleep(0.05)
            await workflow_context.send_signal("task_ready", {"task_id": "123"})

        signal_task = asyncio.create_task(send_delayed())
        signal_task.add_done_callback(lambda t: None)

        # Wait for signal
        data = await workflow_context.wait_for_signal("task_ready", timeout=1.0)
        assert isinstance(data, dict) and data["task_id"] == "123"

    async def test_signal_timeout(self, workflow_context: WorkflowContext) -> None:
        """Test signal wait timeout."""
        result = await workflow_context.wait_for_signal("missing_signal", timeout=0.1)
        assert result is None


class TestSignalDecorator:
    """Tests for @signal decorator."""

    def test_signal_decorator_marks_method(self) -> None:
        """Test that @signal decorator marks methods correctly."""

        @signal("test_signal")
        async def handler(data):
            pass

        assert hasattr(handler, "_is_signal")
        assert handler._is_signal is True
        assert handler._signal_name == "test_signal"

    def test_signal_decorator_default_name(self) -> None:
        """Test @signal decorator with default name."""

        @signal()
        async def my_handler(data):
            pass

        assert my_handler._signal_name == "my_handler"


class TestQueryDecorator:
    """Tests for @query decorator."""

    def test_query_decorator_marks_method(self) -> None:
        """Test that @query decorator marks methods correctly."""

        @query("get_status")
        def handler():
            return {"status": "ok"}

        assert hasattr(handler, "_is_query")
        assert handler._is_query is True
        assert handler._query_name == "get_status"

    def test_query_decorator_default_name(self) -> None:
        """Test @query decorator with default name."""

        @query()
        def status():
            return "ok"

        assert status._query_name == "status"


# =============================================================================
# Activity Tests
# =============================================================================


class TestInitializeAgentActivity:
    """Tests for InitializeAgentActivity."""

    def test_activity_properties(self) -> None:
        """Test activity properties."""
        activity = InitializeAgentActivity()
        assert activity.name == "initialize_agent"
        assert activity.timeout_seconds == 30.0

    async def test_successful_initialization(
        self, agent_config: AgentConfig, workflow_context: WorkflowContext
    ) -> None:
        """Test successful agent initialization."""
        activity = InitializeAgentActivity()
        result = await activity.execute(agent_config, workflow_context)

        assert result["status"] == "initialized"
        assert result["agent_id"] == "test-agent-001"
        assert "compute" in result["capabilities"]
        assert result["constitutional_hash"] == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_constitutional_hash_mismatch(self, workflow_context: WorkflowContext) -> None:
        """Test initialization fails with wrong constitutional hash."""
        config = AgentConfig(
            agent_id="agent-1",
            agent_type="worker",
            constitutional_hash="invalid-hash",
        )
        activity = InitializeAgentActivity()

        with pytest.raises((ValueError, ACGSConstitutionalViolationError, ACGSValidationError)):
            await activity.execute(config, workflow_context)


class TestExecuteTaskActivity:
    """Tests for ExecuteTaskActivity."""

    def test_activity_properties(self) -> None:
        """Test activity properties."""
        activity = ExecuteTaskActivity()
        assert activity.name == "execute_task"
        assert activity.timeout_seconds == 300.0

    async def test_successful_task_execution(
        self, sample_task: Task, workflow_context: WorkflowContext
    ) -> None:
        """Test successful task execution."""
        activity = ExecuteTaskActivity()
        result = await activity.execute(sample_task, workflow_context)

        assert result.task_id == "task-001"
        assert result.success is True
        assert result.result["processed"] is True
        assert result.duration_ms > 0

    async def test_task_constitutional_hash_mismatch(
        self, workflow_context: WorkflowContext
    ) -> None:
        """Test task fails with wrong constitutional hash."""
        task = Task(
            task_id="task-bad",
            task_type="compute",
            constitutional_hash="bad-hash",
        )
        activity = ExecuteTaskActivity()
        result = await activity.execute(task, workflow_context)

        assert result.success is False
        assert "Constitutional hash mismatch" in result.error


class TestCheckpointAgentActivity:
    """Tests for CheckpointAgentActivity."""

    def test_activity_properties(self) -> None:
        """Test activity properties."""
        activity = CheckpointAgentActivity()
        assert activity.name == "checkpoint_agent"
        assert activity.timeout_seconds == 10.0

    async def test_create_checkpoint(self, workflow_context: WorkflowContext) -> None:
        """Test checkpoint creation."""
        status = AgentStatus(
            agent_id="agent-001",
            state=AgentState.IDLE,
            tasks_completed=5,
        )
        activity = CheckpointAgentActivity()
        checkpoint = await activity.execute(status, workflow_context)

        assert checkpoint["agent_id"] == "agent-001"
        assert checkpoint["state"] == "idle"
        assert checkpoint["tasks_completed"] == 5
        assert "checkpoint_id" in checkpoint
        assert "checkpoint_time" in checkpoint


class TestShutdownAgentActivity:
    """Tests for ShutdownAgentActivity."""

    def test_activity_properties(self) -> None:
        """Test activity properties."""
        activity = ShutdownAgentActivity()
        assert activity.name == "shutdown_agent"
        assert activity.timeout_seconds == 30.0

    async def test_shutdown(self, workflow_context: WorkflowContext) -> None:
        """Test agent shutdown."""
        activity = ShutdownAgentActivity()
        request = ShutdownRequest(agent_id="agent-001", reason="idle_timeout")
        result = await activity.execute(request, workflow_context)

        assert result["status"] == "shutdown"
        assert result["agent_id"] == "agent-001"
        assert result["reason"] == "idle_timeout"
        assert "shutdown_at" in result


# =============================================================================
# Agent Entity Workflow Tests
# =============================================================================


class TestAgentEntityWorkflowInitialization:
    """Tests for AgentEntityWorkflow initialization."""

    def test_workflow_name(self) -> None:
        """Test workflow name property."""
        workflow = AgentEntityWorkflow()
        assert workflow.name == "AgentEntityWorkflow"

    def test_initial_state(self) -> None:
        """Test workflow initial state."""
        workflow = AgentEntityWorkflow()
        assert workflow.state == AgentState.INITIALIZING
        assert workflow.config is None

    def test_signals_registered(self) -> None:
        """Test that signals are registered."""
        workflow = AgentEntityWorkflow()
        signals = workflow.get_signals()
        assert "assign_task" in signals
        assert "suspend" in signals
        assert "resume" in signals
        assert "shutdown" in signals
        assert "update_config" in signals

    def test_queries_registered(self) -> None:
        """Test that queries are registered."""
        workflow = AgentEntityWorkflow()
        queries = workflow.get_queries()
        assert "get_status" in queries
        assert "get_state" in queries
        assert "get_task_results" in queries
        assert "get_pending_tasks" in queries
        assert "get_checkpoints" in queries


class TestAgentEntityWorkflowLifecycle:
    """Tests for AgentEntityWorkflow lifecycle."""

    async def test_basic_lifecycle(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test basic workflow lifecycle with shutdown."""
        workflow = AgentEntityWorkflow()

        # Start workflow
        run_id = await workflow_executor.start(workflow, "wf-test-001", agent_config)
        assert run_id is not None

        # Give workflow time to initialize
        await asyncio.sleep(0.1)

        # Query status
        status = await workflow_executor.query("wf-test-001", "get_status")
        assert status is not None and isinstance(status, AgentStatus)
        assert status.agent_id == "test-agent-001"
        assert status.state in [AgentState.IDLE, AgentState.INITIALIZING]

        # Send shutdown signal
        await workflow_executor.send_signal("wf-test-001", "shutdown", "test_complete")

        # Wait for completion
        result = await workflow_executor.get_result("wf-test-001", timeout=5.0)
        assert result is not None and isinstance(result, AgentResult)
        assert result.agent_id == "test-agent-001"
        assert result.final_state == AgentState.TERMINATED

    async def test_task_processing(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
        sample_task: Task,
    ) -> None:
        """Test task assignment and processing."""
        workflow = AgentEntityWorkflow()

        # Start workflow
        await workflow_executor.start(workflow, "wf-task-test", agent_config)
        await asyncio.sleep(0.1)

        # Assign task
        await workflow_executor.send_signal(
            "wf-task-test",
            "assign_task",
            sample_task,  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.2)

        # Query task results
        results = await workflow_executor.query("wf-task-test", "get_task_results")
        assert results is not None and isinstance(results, list)
        assert len(results) >= 1
        assert results[0].success is True  # type: ignore[union-attr]

        # Shutdown
        await workflow_executor.send_signal("wf-task-test", "shutdown", "complete")
        result = await workflow_executor.get_result("wf-task-test", timeout=5.0)
        assert result is not None and isinstance(result, AgentResult)
        assert result.total_tasks_completed >= 1

    async def test_suspend_and_resume(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test suspend and resume functionality."""
        workflow = AgentEntityWorkflow()

        await workflow_executor.start(workflow, "wf-suspend-test", agent_config)
        await asyncio.sleep(0.2)

        # Suspend
        await workflow_executor.send_signal("wf-suspend-test", "suspend", "maintenance")

        # Wait for the workflow to process the suspend signal
        for _ in range(10):
            await asyncio.sleep(0.1)
            state = await workflow_executor.query("wf-suspend-test", "get_state")
            if state == AgentState.SUSPENDED:
                break

        assert state == AgentState.SUSPENDED

        # Resume
        await workflow_executor.send_signal("wf-suspend-test", "resume")

        # Wait for the workflow to process the resume signal
        for _ in range(10):
            await asyncio.sleep(0.1)
            state = await workflow_executor.query("wf-suspend-test", "get_state")
            if state == AgentState.IDLE:
                break

        assert state == AgentState.IDLE

        # Cleanup
        await workflow_executor.send_signal("wf-suspend-test", "shutdown")
        await workflow_executor.get_result("wf-suspend-test", timeout=5.0)

    async def test_multiple_tasks(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test processing multiple tasks."""
        workflow = AgentEntityWorkflow()

        await workflow_executor.start(workflow, "wf-multi-test", agent_config)
        await asyncio.sleep(0.1)

        # Assign multiple tasks
        for i in range(3):
            task = Task(
                task_id=f"task-{i}",
                task_type="compute",
                payload={"index": i},
            )
            await workflow_executor.send_signal(
                "wf-multi-test",
                "assign_task",
                task,  # type: ignore[arg-type]
            )

        # Wait for processing
        await asyncio.sleep(0.5)

        # Query results
        status = await workflow_executor.query("wf-multi-test", "get_status")
        assert status is not None and isinstance(status, AgentStatus)
        assert status.tasks_completed >= 3

        # Cleanup
        await workflow_executor.send_signal("wf-multi-test", "shutdown")
        result = await workflow_executor.get_result("wf-multi-test", timeout=5.0)
        assert result is not None and isinstance(result, AgentResult)
        assert result.total_tasks_completed >= 3


class TestAgentEntityWorkflowSignals:
    """Tests for AgentEntityWorkflow signal handlers."""

    async def test_assign_task_signal(self) -> None:
        """Test assign_task signal handler."""
        workflow = AgentEntityWorkflow()
        workflow.context = WorkflowContext(workflow_id="test")

        task = Task(task_id="signal-task", task_type="test")
        await workflow.assign_task(task)

        pending = workflow.get_pending_tasks()
        assert pending == 1

    async def test_shutdown_signal(self) -> None:
        """Test shutdown signal handler."""
        workflow = AgentEntityWorkflow()
        workflow.context = WorkflowContext(workflow_id="test")

        await workflow.shutdown("test_shutdown")

        assert workflow._shutdown_requested is True
        assert workflow._shutdown_reason == "test_shutdown"

    async def test_update_config_signal(self, agent_config: AgentConfig) -> None:
        """Test update_config signal handler."""
        workflow = AgentEntityWorkflow()
        workflow.context = WorkflowContext(workflow_id="test")
        workflow._config = agent_config

        await workflow.update_config({"max_concurrent_tasks": 10})

        assert workflow._config.max_concurrent_tasks == 10


class TestAgentEntityWorkflowQueries:
    """Tests for AgentEntityWorkflow query handlers."""

    def test_get_status_query(self, agent_config: AgentConfig) -> None:
        """Test get_status query handler."""
        workflow = AgentEntityWorkflow()
        workflow._config = agent_config
        workflow._state = AgentState.IDLE
        workflow._tasks_completed = 5

        status = workflow.get_status()

        assert status.agent_id == "test-agent-001"
        assert status.state == AgentState.IDLE
        assert status.tasks_completed == 5

    def test_get_state_query(self) -> None:
        """Test get_state query handler."""
        workflow = AgentEntityWorkflow()
        workflow._state = AgentState.PROCESSING

        state = workflow.get_state()

        assert state == AgentState.PROCESSING

    def test_get_task_results_query(self) -> None:
        """Test get_task_results query handler."""
        workflow = AgentEntityWorkflow()
        workflow._task_results = [
            TaskResult(task_id="t1", success=True),
            TaskResult(task_id="t2", success=False),
        ]

        results = workflow.get_task_results()

        assert len(results) == 2
        assert results[0].task_id == "t1"

    def test_get_pending_tasks_query(self) -> None:
        """Test get_pending_tasks query handler."""
        workflow = AgentEntityWorkflow()

        # Queue is empty initially
        pending = workflow.get_pending_tasks()
        assert pending == 0

    def test_get_checkpoints_query(self) -> None:
        """Test get_checkpoints query handler."""
        workflow = AgentEntityWorkflow()
        workflow._checkpoints = [{"checkpoint_id": "cp1"}]

        checkpoints = workflow.get_checkpoints()

        assert len(checkpoints) == 1
        assert checkpoints[0]["checkpoint_id"] == "cp1"


# =============================================================================
# In-Memory Workflow Executor Tests
# =============================================================================


class TestInMemoryWorkflowExecutor:
    """Tests for InMemoryWorkflowExecutor."""

    async def test_start_workflow(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test starting a workflow."""
        workflow = AgentEntityWorkflow()
        run_id = await workflow_executor.start(workflow, "test-wf", agent_config)

        assert run_id is not None
        assert workflow_executor.get_status("test-wf") == WorkflowStatus.RUNNING

        # Cleanup
        await workflow_executor.cancel("test-wf")

    async def test_cancel_workflow(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test cancelling a workflow."""
        workflow = AgentEntityWorkflow()
        await workflow_executor.start(workflow, "cancel-wf", agent_config)

        await workflow_executor.cancel("cancel-wf")

        status = workflow_executor.get_status("cancel-wf")
        assert status == WorkflowStatus.CANCELLED

    async def test_query_nonexistent_workflow(
        self, workflow_executor: InMemoryWorkflowExecutor
    ) -> None:
        """Test querying a non-existent workflow."""
        with pytest.raises((ValueError, ACGSValidationError, ACGSResourceNotFoundError)):
            await workflow_executor.query("nonexistent", "get_status")

    async def test_send_signal_nonexistent_workflow(
        self, workflow_executor: InMemoryWorkflowExecutor
    ) -> None:
        """Test sending signal to non-existent workflow."""
        with pytest.raises((ValueError, ACGSValidationError, ACGSResourceNotFoundError)):
            await workflow_executor.send_signal("nonexistent", "shutdown")

    async def test_get_context(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test getting workflow context."""
        workflow = AgentEntityWorkflow()
        await workflow_executor.start(workflow, "context-wf", agent_config)

        context = workflow_executor.get_context("context-wf")
        assert context.workflow_id == "context-wf"
        assert context.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

        # Cleanup
        await workflow_executor.cancel("context-wf")


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_task_priority_ordering(self) -> None:
        """Test task priority values."""
        assert TaskPriority.LOW.value < TaskPriority.NORMAL.value
        assert TaskPriority.NORMAL.value < TaskPriority.HIGH.value
        assert TaskPriority.HIGH.value < TaskPriority.CRITICAL.value

    def test_agent_state_transitions(self) -> None:
        """Test agent state enum values."""
        states = [s.value for s in AgentState]
        assert "initializing" in states
        assert "idle" in states
        assert "processing" in states
        assert "terminated" in states

    def test_workflow_activity_base_class(self) -> None:
        """Test WorkflowActivity base class."""

        # Create a custom activity subclass
        class CustomActivity(WorkflowActivity):
            activity_name = "custom_activity"
            activity_timeout_seconds = 120.0

        activity = CustomActivity()
        assert activity.name == "custom_activity"
        assert activity.timeout_seconds == 120.0

    def test_activity_instances_exist(self) -> None:
        """Test that activity instances are available."""
        assert initialize_agent_activity is not None
        assert execute_task_activity is not None
        assert checkpoint_agent_activity is not None
        assert shutdown_agent_activity is not None

    async def test_workflow_without_context(self) -> None:
        """Test workflow access without context raises error."""
        workflow = AgentEntityWorkflow()

        with pytest.raises((RuntimeError, ACGSServiceUnavailableError)):
            _ = workflow.context

    def test_empty_agent_config(self) -> None:
        """Test minimal agent config."""
        config = AgentConfig(agent_id="", agent_type="")
        assert config.agent_id == ""
        assert config.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret

    async def test_task_with_retry(
        self,
        workflow_executor: InMemoryWorkflowExecutor,
        agent_config: AgentConfig,
    ) -> None:
        """Test task retry behavior."""
        workflow = AgentEntityWorkflow()
        await workflow_executor.start(workflow, "retry-wf", agent_config)
        await asyncio.sleep(0.1)

        # Task with retries configured
        task = Task(
            task_id="retry-task",
            task_type="compute",
            max_retries=3,
        )
        await workflow_executor.send_signal(
            "retry-wf",
            "assign_task",
            task,  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.2)

        # Cleanup
        await workflow_executor.send_signal("retry-wf", "shutdown")
        await workflow_executor.get_result("retry-wf", timeout=5.0)


class TestConstitutionalCompliance:
    """Tests for constitutional compliance."""

    def test_all_dataclasses_have_constitutional_hash(self) -> None:
        """Test that all data classes include constitutional hash."""
        config = AgentConfig(agent_id="a", agent_type="t")
        task = Task()
        result = TaskResult(task_id="t", success=True)
        status = AgentStatus(agent_id="a", state=AgentState.IDLE)
        agent_result = AgentResult(agent_id="a", final_state=AgentState.TERMINATED)

        expected_hash = CONSTITUTIONAL_HASH  # pragma: allowlist secret
        assert config.constitutional_hash == expected_hash
        assert task.constitutional_hash == expected_hash
        assert result.constitutional_hash == expected_hash
        assert status.constitutional_hash == expected_hash
        assert agent_result.constitutional_hash == expected_hash

    def test_workflow_context_constitutional_hash(self) -> None:
        """Test workflow context has constitutional hash."""
        context = WorkflowContext(workflow_id="test")
        assert context.constitutional_hash == CONSTITUTIONAL_HASH  # pragma: allowlist secret


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkflowIntegration:
    """Integration tests for workflow system."""

    async def test_full_workflow_cycle(self, workflow_executor: InMemoryWorkflowExecutor) -> None:
        """Test complete workflow cycle with all operations."""
        config = AgentConfig(
            agent_id="integration-agent",
            agent_type="worker",
            capabilities=["test"],
            idle_timeout_seconds=30.0,
        )
        workflow = AgentEntityWorkflow()

        # Start
        await workflow_executor.start(workflow, "integration-wf", config)
        await asyncio.sleep(0.1)

        # Verify running
        status = workflow_executor.get_status("integration-wf")
        assert status == WorkflowStatus.RUNNING

        # Assign tasks
        for i in range(2):
            task = Task(task_id=f"int-task-{i}", task_type="test")
            await workflow_executor.send_signal(
                "integration-wf",
                "assign_task",
                task,  # type: ignore[arg-type]
            )

        await asyncio.sleep(0.3)

        # Query state
        agent_status = await workflow_executor.query("integration-wf", "get_status")
        assert agent_status is not None and isinstance(agent_status, AgentStatus)
        assert agent_status.tasks_completed >= 2

        # Check checkpoints
        checkpoints = await workflow_executor.query("integration-wf", "get_checkpoints")
        assert checkpoints is not None and isinstance(checkpoints, list)
        assert len(checkpoints) >= 1

        # Shutdown
        await workflow_executor.send_signal("integration-wf", "shutdown", "complete")
        result = await workflow_executor.get_result("integration-wf", timeout=5.0)
        assert result is not None and isinstance(result, AgentResult)
        assert result.agent_id == "integration-agent"
        assert result.final_state == AgentState.TERMINATED
        assert result.total_tasks_completed >= 2
        assert result.shutdown_reason == "complete"
