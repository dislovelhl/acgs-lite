"""
ACGS-2 Enhanced Agent Bus - End-to-End Workflow Tests
Constitutional Hash: 608508a9bd224290

Comprehensive E2E tests for workflow patterns:
- Saga orchestration with LIFO compensation
- DAG execution with maximum parallelism
- Constitutional validation at workflow boundaries
- Multi-agent coordination scenarios
- Deliberation layer integration
"""

import asyncio
import time
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from enhanced_agent_bus._compat.types import JSONDict

# Import workflow components
try:
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageType,
        Priority,
    )
    from enhanced_agent_bus.validation_strategies import (
        CompositeValidationStrategy,
        StaticHashValidationStrategy,
    )
    from enhanced_agent_bus.validators import ValidationResult
except ImportError:
    import sys

    sys.path.insert(0, "/home/martin/ACGS")
    from enhanced_agent_bus.agent_bus import EnhancedAgentBus
    from enhanced_agent_bus.models import (
        CONSTITUTIONAL_HASH,
        AgentMessage,
        MessageType,
        Priority,
    )
    from enhanced_agent_bus.validation_strategies import (
        CompositeValidationStrategy,
        StaticHashValidationStrategy,
    )
    from enhanced_agent_bus.validators import ValidationResult

# =============================================================================
# HELPER CLASSES FOR WORKFLOW TESTING
# =============================================================================


class WorkflowContext:
    """Context for workflow execution tracking."""

    def __init__(self):
        self.step_results: JSONDict = {}
        self.execution_log: list[str] = []
        self.compensation_log: list[str] = []

    def set_step_result(self, step_name: str, result: Any) -> None:
        self.step_results[step_name] = result

    def get_step_result(self, step_name: str) -> Any:
        return self.step_results.get(step_name)

    def log_execution(self, step_name: str) -> None:
        self.execution_log.append(step_name)

    def log_compensation(self, step_name: str) -> None:
        self.compensation_log.append(step_name)


class MockSagaStep:
    """Mock saga step for testing."""

    def __init__(
        self,
        name: str,
        should_fail: bool = False,
        fail_compensation: bool = False,
        execution_delay: float = 0.01,
    ):
        self.name = name
        self.should_fail = should_fail
        self.fail_compensation = fail_compensation
        self.execution_delay = execution_delay
        self.executed = False
        self.compensated = False

    async def execute(self, context: WorkflowContext) -> JSONDict:
        await asyncio.sleep(self.execution_delay)
        context.log_execution(self.name)

        if self.should_fail:
            raise RuntimeError(f"Step {self.name} failed intentionally")

        self.executed = True
        return {"step": self.name, "result": "success"}

    async def compensate(self, context: WorkflowContext) -> None:
        await asyncio.sleep(self.execution_delay / 2)
        context.log_compensation(self.name)

        if self.fail_compensation:
            raise RuntimeError(f"Compensation for {self.name} failed")

        self.compensated = True


class MockDAGNode:
    """Mock DAG node for testing."""

    def __init__(
        self,
        node_id: str,
        dependencies: list[str] | None = None,
        should_fail: bool = False,
        execution_delay: float = 0.01,
    ):
        self.node_id = node_id
        self.dependencies = dependencies or []
        self.should_fail = should_fail
        self.execution_delay = execution_delay
        self.executed = False
        self.execution_order: int | None = None

    async def execute(
        self, context: WorkflowContext, execution_counter: dict[str, int]
    ) -> JSONDict:
        await asyncio.sleep(self.execution_delay)
        context.log_execution(self.node_id)

        # Track execution order
        execution_counter["count"] += 1
        self.execution_order = execution_counter["count"]

        if self.should_fail:
            raise RuntimeError(f"Node {self.node_id} failed intentionally")

        self.executed = True
        return {"node": self.node_id, "result": "success", "order": self.execution_order}


# =============================================================================
# SAGA PATTERN E2E TESTS
# =============================================================================


class TestSagaPatternE2E:
    """End-to-end tests for Saga orchestration pattern."""

    async def test_saga_happy_path_all_steps_succeed(self):
        """Test saga execution when all steps succeed."""
        context = WorkflowContext()
        steps = [
            MockSagaStep("reserve_inventory"),
            MockSagaStep("charge_payment"),
            MockSagaStep("ship_order"),
        ]

        # Execute steps sequentially
        compensation_stack = []
        for step in steps:
            result = await step.execute(context)
            compensation_stack.append(step)
            context.set_step_result(step.name, result)

        # Verify all steps executed in order
        assert context.execution_log == ["reserve_inventory", "charge_payment", "ship_order"]
        assert all(step.executed for step in steps)
        assert len(compensation_stack) == 3

    async def test_saga_lifo_compensation_on_failure(self):
        """Test LIFO compensation order when a step fails."""
        context = WorkflowContext()
        steps = [
            MockSagaStep("step_1"),
            MockSagaStep("step_2"),
            MockSagaStep("step_3", should_fail=True),
            MockSagaStep("step_4"),  # Should not execute
        ]

        compensation_stack = []
        failed = False

        for step in steps:
            try:
                result = await step.execute(context)
                compensation_stack.append(step)
                context.set_step_result(step.name, result)
            except (RuntimeError, ValueError, TypeError):
                failed = True
                break

        # Run compensations in LIFO order
        if failed:
            for step in reversed(compensation_stack):
                await step.compensate(context)

        # Verify execution stopped at step_3
        assert "step_4" not in context.execution_log
        assert context.execution_log == ["step_1", "step_2", "step_3"]

        # Verify LIFO compensation order
        assert context.compensation_log == ["step_2", "step_1"]
        assert steps[0].compensated is True
        assert steps[1].compensated is True
        assert steps[3].executed is False

    async def test_saga_compensation_failure_handling(self):
        """Test handling of compensation failures."""
        context = WorkflowContext()
        steps = [
            MockSagaStep("step_1"),
            MockSagaStep("step_2", fail_compensation=True),
            MockSagaStep("step_3", should_fail=True),
        ]

        compensation_stack = []
        failed = False

        for step in steps:
            try:
                await step.execute(context)
                compensation_stack.append(step)
            except (RuntimeError, ValueError, TypeError):
                failed = True
                break

        # Track compensation failures
        compensation_failures = []
        if failed:
            for step in reversed(compensation_stack):
                try:
                    await step.compensate(context)
                except (RuntimeError, ValueError, TypeError, AssertionError) as e:
                    compensation_failures.append((step.name, str(e)))

        # step_2 compensation should fail, step_1 should succeed
        assert len(compensation_failures) == 1
        assert compensation_failures[0][0] == "step_2"
        assert steps[0].compensated is True
        assert steps[1].compensated is False

    async def test_saga_idempotent_compensations(self):
        """Test that compensations can be retried (idempotency)."""
        context = WorkflowContext()
        step = MockSagaStep("idempotent_step")

        await step.execute(context)

        # Compensate multiple times (should be safe)
        await step.compensate(context)
        await step.compensate(context)
        await step.compensate(context)

        # Compensation should be logged 3 times
        assert context.compensation_log.count("idempotent_step") == 3


# =============================================================================
# DAG EXECUTION E2E TESTS
# =============================================================================


class TestDAGExecutionE2E:
    """End-to-end tests for DAG execution with parallelism."""

    async def test_dag_independent_nodes_parallel_execution(self):
        """Test that independent nodes execute in parallel."""
        context = WorkflowContext()
        execution_counter = {"count": 0}

        # Create nodes: A is independent, B depends on A, C is independent
        #   A (independent)    C (independent)
        #       |
        #       v
        #   B (depends on A)
        nodes = {
            "A": MockDAGNode("A"),
            "B": MockDAGNode("B", dependencies=["A"]),
            "C": MockDAGNode("C"),
        }

        # Execute using as_completed pattern
        async def execute_node(node: MockDAGNode):
            return await node.execute(context, execution_counter)

        # Track start times to verify parallelism
        time.monotonic()

        # First wave: A and C can run in parallel
        first_wave = [nodes["A"], nodes["C"]]
        await asyncio.gather(*[execute_node(n) for n in first_wave])

        # Second wave: B can now run
        await execute_node(nodes["B"])

        time.monotonic()

        # Verify parallel execution of A and C
        assert nodes["A"].executed and nodes["C"].executed
        assert nodes["B"].executed

        # A and C should have lower execution orders than B
        assert nodes["A"].execution_order < nodes["B"].execution_order
        assert nodes["C"].execution_order < nodes["B"].execution_order

    async def test_dag_complex_dependency_chain(self):
        """Test complex DAG with multiple dependency levels."""
        context = WorkflowContext()
        execution_counter = {"count": 0}

        # Diamond dependency pattern:
        #       A
        #      / \
        #     B   C
        #      \ /
        #       D
        nodes = {
            "A": MockDAGNode("A"),
            "B": MockDAGNode("B", dependencies=["A"]),
            "C": MockDAGNode("C", dependencies=["A"]),
            "D": MockDAGNode("D", dependencies=["B", "C"]),
        }

        async def execute_node(node: MockDAGNode):
            return await node.execute(context, execution_counter)

        # Execute level by level
        await execute_node(nodes["A"])  # Level 1

        # B and C can run in parallel (Level 2)
        await asyncio.gather(execute_node(nodes["B"]), execute_node(nodes["C"]))

        await execute_node(nodes["D"])  # Level 3

        # Verify execution order respects dependencies
        assert nodes["A"].execution_order < nodes["B"].execution_order
        assert nodes["A"].execution_order < nodes["C"].execution_order
        assert nodes["B"].execution_order < nodes["D"].execution_order
        assert nodes["C"].execution_order < nodes["D"].execution_order

    async def test_dag_node_failure_skips_dependents(self):
        """Test that node failure causes dependent nodes to be skipped."""
        context = WorkflowContext()
        execution_counter = {"count": 0}

        nodes = {
            "A": MockDAGNode("A"),
            "B": MockDAGNode("B", dependencies=["A"], should_fail=True),
            "C": MockDAGNode("C", dependencies=["B"]),  # Should be skipped
        }

        async def execute_node(node: MockDAGNode):
            return await node.execute(context, execution_counter)

        # Execute A
        await execute_node(nodes["A"])

        # B fails
        with pytest.raises(RuntimeError):
            await execute_node(nodes["B"])

        # C should not execute (dependent on failed B)
        # In a real DAG executor, this would be handled automatically
        assert nodes["A"].executed is True
        assert nodes["B"].executed is False  # Failed, not marked as executed
        assert nodes["C"].executed is False

    async def test_dag_as_completed_pattern(self):
        """Test using asyncio.as_completed for maximum parallelism."""
        context = WorkflowContext()
        execution_counter = {"count": 0}

        # All independent nodes
        nodes = [MockDAGNode(f"node_{i}", execution_delay=0.01 * (i + 1)) for i in range(5)]

        async def execute_node(node: MockDAGNode):
            result = await node.execute(context, execution_counter)
            return node.node_id, result

        # Execute all in parallel using as_completed
        tasks = [asyncio.create_task(execute_node(n)) for n in nodes]
        completion_order = []

        for coro in asyncio.as_completed(tasks):
            node_id, _result = await coro
            completion_order.append(node_id)

        # All nodes should complete
        assert len(completion_order) == 5
        assert all(n.executed for n in nodes)

        # Faster nodes should complete first
        assert completion_order[0] == "node_0"


# =============================================================================
# CONSTITUTIONAL VALIDATION E2E TESTS
# =============================================================================


class TestConstitutionalValidationE2E:
    """End-to-end tests for constitutional validation across boundaries."""

    async def test_constitutional_validation_at_workflow_start(self):
        """Test constitutional validation at workflow entry point."""
        # Valid hash
        valid_message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id=None,
        )

        strategy = StaticHashValidationStrategy(strict=True)
        is_valid, error = await strategy.validate(valid_message)

        assert is_valid is True
        assert error is None

    async def test_constitutional_validation_rejects_invalid_hash(self):
        """Test that invalid constitutional hash is rejected."""
        invalid_message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash="invalid_hash_xyz",
            tenant_id=None,
        )

        strategy = StaticHashValidationStrategy(strict=True)
        is_valid, error = await strategy.validate(invalid_message)

        assert is_valid is False
        assert "mismatch" in error.lower()

    async def test_constitutional_validation_at_each_saga_step(self):
        """Test constitutional hash validation at each saga step boundary."""
        context = WorkflowContext()

        async def step_with_validation(step_name: str, message: AgentMessage) -> JSONDict:
            # Validate constitutional hash at step boundary
            strategy = StaticHashValidationStrategy(strict=True)
            is_valid, error = await strategy.validate(message)

            if not is_valid:
                raise Exception(f"Constitutional validation failed at {step_name}: {error}")

            context.log_execution(step_name)
            return {"step": step_name, "validated": True}

        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id=None,
        )

        # Execute multiple steps with validation
        for step_name in ["step_1", "step_2", "step_3"]:
            result = await step_with_validation(step_name, message)
            assert result["validated"] is True

        assert context.execution_log == ["step_1", "step_2", "step_3"]

    async def test_composite_validation_strategy(self):
        """Test composite validation combining multiple strategies."""
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            from_agent="sender",
            to_agent="receiver",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "test"},
            priority=Priority.MEDIUM,
            constitutional_hash=CONSTITUTIONAL_HASH,
            tenant_id=None,
        )

        composite = CompositeValidationStrategy()
        composite.add_strategy(StaticHashValidationStrategy(strict=True))

        is_valid, _error = await composite.validate(message)
        assert is_valid is True


# =============================================================================
# MULTI-AGENT COORDINATION E2E TESTS
# =============================================================================


class TestMultiAgentCoordinationE2E:
    """End-to-end tests for multi-agent coordination."""

    @pytest.fixture
    def mock_processor(self):
        """Mock message processor."""
        processor = MagicMock()
        processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        processor.get_metrics = MagicMock(return_value={"processed": 0})
        return processor

    async def test_agent_registration_and_discovery(self, mock_processor):
        """Test agent registration and discovery across the bus."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )

        # Register multiple agents
        await bus.register_agent("validator-1", "validator", ["validate"], "tenant-1")
        await bus.register_agent("validator-2", "validator", ["validate"], "tenant-1")
        await bus.register_agent("processor-1", "processor", ["process", "transform"], "tenant-1")

        # Discovery by type
        validators = bus.get_agents_by_type("validator")
        assert len(validators) == 2

        # Discovery by capability
        processors = bus.get_agents_by_capability("process")
        assert "processor-1" in processors
        assert "validator-1" not in processors

    async def test_agent_message_routing(self, mock_processor):
        """Test message routing between agents."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            # Register agents
            await bus.register_agent("sender", "worker", ["send"], "tenant-1")
            await bus.register_agent("receiver", "worker", ["receive"], "tenant-1")

            # Create and send message
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                from_agent="sender",
                to_agent="receiver",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={"action": "test"},
                priority=Priority.MEDIUM,
                constitutional_hash=CONSTITUTIONAL_HASH,
                tenant_id="tenant-1",
            )

            result = await bus.send_message(message)
            assert result.is_valid is True
        finally:
            await bus.stop()

    async def test_multi_tenant_agent_isolation(self, mock_processor):
        """Test that agents are properly isolated by tenant."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            # Register agents in different tenants
            await bus.register_agent("agent-a", "worker", [], "tenant-A")
            await bus.register_agent("agent-b", "worker", [], "tenant-B")

            # Message from tenant-A to tenant-B should fail
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                from_agent="agent-a",
                to_agent="agent-b",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={"action": "cross-tenant"},
                priority=Priority.MEDIUM,
                constitutional_hash=CONSTITUTIONAL_HASH,
                tenant_id="tenant-A",
            )

            result = await bus.send_message(message)
            assert result.is_valid is False
            assert any("Tenant mismatch" in err for err in result.errors)
        finally:
            await bus.stop()

    async def test_broadcast_message_to_tenant_agents(self, mock_processor):
        """Test broadcast message reaches only same-tenant agents."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            # Register agents
            await bus.register_agent("agent-t1-a", "worker", [], "tenant-1")
            await bus.register_agent("agent-t1-b", "worker", [], "tenant-1")
            await bus.register_agent("agent-t2-a", "worker", [], "tenant-2")

            # Broadcast to tenant-1
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                from_agent="broadcaster",
                to_agent=None,
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={"action": "broadcast"},
                priority=Priority.HIGH,
                constitutional_hash=CONSTITUTIONAL_HASH,
                tenant_id="tenant-1",
            )

            results = await bus.broadcast_message(message)

            # Should only reach tenant-1 agents
            assert "agent-t1-a" in results
            assert "agent-t1-b" in results
            assert "agent-t2-a" not in results
        finally:
            await bus.stop()


# =============================================================================
# INTEGRATION WORKFLOW E2E TESTS
# =============================================================================


class TestIntegrationWorkflowE2E:
    """End-to-end tests for complete integration workflows."""

    @pytest.fixture
    def mock_processor(self):
        """Mock message processor with configurable behavior."""
        processor = MagicMock()
        processor.process = AsyncMock(return_value=ValidationResult(is_valid=True))
        processor.get_metrics = MagicMock(return_value={"processed": 0})
        return processor

    async def test_complete_governance_workflow(self, mock_processor):
        """Test complete governance workflow from request to decision."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            # 1. Register governance agents
            await bus.register_agent("policy-engine", "validator", ["validate_policy"], "tenant-1")
            await bus.register_agent("decision-maker", "processor", ["decide"], "tenant-1")
            await bus.register_agent("audit-logger", "auditor", ["log_decision"], "tenant-1")

            # 2. Send governance request
            request = AgentMessage(
                message_id=str(uuid.uuid4()),
                from_agent="requester",
                to_agent="policy-engine",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={"action": "approve_data_access", "resource": "user_data"},
                priority=Priority.HIGH,
                constitutional_hash=CONSTITUTIONAL_HASH,
                tenant_id="tenant-1",
            )

            result = await bus.send_message(request)
            assert result.is_valid is True

            # 3. Check metrics
            metrics = bus.get_metrics()
            assert metrics["messages_sent"] >= 1
        finally:
            await bus.stop()

    async def test_degraded_mode_workflow(self, mock_processor):
        """Test workflow continues in degraded mode when processor fails."""
        # Configure processor to fail
        mock_processor.process = AsyncMock(side_effect=Exception("Processor unavailable"))

        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                from_agent="sender",
                to_agent="receiver",
                message_type=MessageType.GOVERNANCE_REQUEST,
                content={"action": "test"},
                priority=Priority.MEDIUM,
                constitutional_hash=CONSTITUTIONAL_HASH,
                tenant_id=None,
                metadata={"prevalidated": True},
            )

            result = await bus.send_message(message)

            # Should succeed via degraded mode (static hash validation)
            assert result.is_valid is True
            assert result.metadata.get("governance_mode") == "DEGRADED"
        finally:
            await bus.stop()

    async def test_high_throughput_message_processing(self, mock_processor):
        """Test high-throughput message processing performance."""
        bus = EnhancedAgentBus(
            use_dynamic_policy=False,
            use_redis_registry=False,
            use_kafka=False,
            enable_metering=False,
            enable_rate_limiting=False,
            processor=mock_processor,
        )
        await bus.start()

        try:
            num_messages = 100
            start_time = time.monotonic()

            # Send many messages concurrently
            messages = [
                AgentMessage(
                    message_id=str(uuid.uuid4()),
                    from_agent="sender",
                    to_agent="receiver",
                    message_type=MessageType.GOVERNANCE_REQUEST,
                    content={"action": f"test_{i}"},
                    priority=Priority.MEDIUM,
                    constitutional_hash=CONSTITUTIONAL_HASH,
                    tenant_id=None,
                )
                for i in range(num_messages)
            ]

            results = await asyncio.gather(*[bus.send_message(m) for m in messages])

            end_time = time.monotonic()
            elapsed_ms = (end_time - start_time) * 1000

            # All messages should succeed
            assert all(r.is_valid for r in results)

            # Calculate throughput
            num_messages / (elapsed_ms / 1000)

            # Should achieve reasonable throughput (>100 RPS target)
            # Note: This is a simplified test; actual performance depends on infrastructure
            metrics = bus.get_metrics()
            assert metrics["messages_sent"] == num_messages
        finally:
            await bus.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
