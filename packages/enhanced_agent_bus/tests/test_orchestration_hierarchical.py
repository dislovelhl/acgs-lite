"""
Tests for enhanced_agent_bus.orchestration.hierarchical

Covers: SupervisorNode, WorkerNode, HierarchicalOrchestrator,
        task planning, worker selection, delegation, critique,
        handoff contract validation, and end-to-end goal execution.
"""

import pytest

from enhanced_agent_bus.orchestration.hierarchical import (
    HierarchicalOrchestrator,
    NodeStatus,
    SupervisorNode,
    Task,
    WorkerCapability,
    WorkerNode,
)

# ---------------------------------------------------------------------------
# Task and WorkerCapability dataclasses
# ---------------------------------------------------------------------------


class TestTaskDataclass:
    def test_defaults(self):
        t = Task(task_id="t1", description="do thing")
        assert t.priority == 0
        assert t.dependencies == []
        assert t.status == "pending"
        assert t.result is None


class TestWorkerCapability:
    def test_defaults(self):
        wc = WorkerCapability(worker_id="w1", capabilities=["generic"])
        assert wc.capacity == 1
        assert wc.current_load == 0
        assert wc.performance_score == 1.0


class TestNodeStatus:
    def test_values(self):
        assert NodeStatus.IDLE.value == "idle"
        assert NodeStatus.COMPLETED.value == "completed"
        assert NodeStatus.FAILED.value == "failed"


# ---------------------------------------------------------------------------
# SupervisorNode
# ---------------------------------------------------------------------------


class TestSupervisorNode:
    @pytest.fixture()
    def supervisor(self):
        s = SupervisorNode(supervisor_id="sup1")
        s.register_worker("w1", ["generic", "analysis"], capacity=2)
        s.register_worker("w2", ["generic"], capacity=1)
        return s

    def test_register_worker(self, supervisor):
        assert "w1" in supervisor.worker_capabilities
        assert supervisor.worker_capabilities["w1"].capacity == 2

    @pytest.mark.asyncio
    async def test_plan_tasks_rule_based(self, supervisor):
        tasks = await supervisor.plan_tasks("do something", {"steps": ["a", "b"]})
        assert len(tasks) == 2
        assert all(t.task_id.startswith("task_") for t in tasks)
        # After planning, status resets to IDLE
        assert supervisor.status == NodeStatus.IDLE

    @pytest.mark.asyncio
    async def test_plan_tasks_single_default_step(self, supervisor):
        tasks = await supervisor.plan_tasks("single goal", {})
        assert len(tasks) == 1

    @pytest.mark.asyncio
    async def test_plan_tasks_with_llm_client(self):
        # LLM client path falls through to rule-based
        sup = SupervisorNode(llm_client=object())
        tasks = await sup.plan_tasks("goal", {"steps": ["x"]})
        assert len(tasks) == 1

    def test_select_worker_generic(self, supervisor):
        task = Task(task_id="t1", description="work", metadata={"task_type": "generic"})
        selected = supervisor.select_worker(task)
        assert selected is not None
        assert selected in ("w1", "w2")

    def test_select_worker_respects_capacity(self, supervisor):
        # Fill w2 to capacity
        supervisor.worker_capabilities["w2"].current_load = 1
        task = Task(task_id="t1", description="work", metadata={"task_type": "generic"})
        selected = supervisor.select_worker(task)
        assert selected == "w1"

    def test_select_worker_no_suitable(self):
        # Create supervisor with no "generic" capability workers
        sup = SupervisorNode()
        sup.register_worker("w_specific", ["analysis_only"], capacity=1)
        task = Task(task_id="t1", description="work", metadata={"task_type": "exotic"})
        selected = sup.select_worker(task)
        assert selected is None

    @pytest.mark.asyncio
    async def test_delegate_task(self, supervisor):
        task = Task(
            task_id="t1",
            description="work",
            metadata={
                "handoff_contract": {
                    "owner": "test",
                    "input_contract": "Task.v1",
                    "done_criteria": "done",
                }
            },
        )
        result = await supervisor.delegate_task(task, "w1")
        assert result["status"] == "delegated"
        assert result["worker_id"] == "w1"
        assert len(supervisor.execution_history) == 1

    @pytest.mark.asyncio
    async def test_delegate_task_handoff_validation_failure(self):
        sup = SupervisorNode(require_handoff_contract=True)
        sup.register_worker("w1", ["generic"])
        task = Task(task_id="t1", description="work", metadata={})
        result = await sup.delegate_task(task, "w1")
        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_delegate_task_handoff_bypassed(self):
        sup = SupervisorNode(require_handoff_contract=False)
        sup.register_worker("w1", ["generic"])
        task = Task(task_id="t1", description="work", metadata={})
        result = await sup.delegate_task(task, "w1")
        assert result["status"] == "delegated"

    def test_validate_handoff_missing_keys(self):
        sup = SupervisorNode(require_handoff_contract=True)
        task = Task(
            task_id="t1",
            description="x",
            metadata={"handoff_contract": {"owner": "a"}},
        )
        valid, detail = sup._validate_handoff_contract(task)
        assert valid is False
        assert "Missing required handoff keys" in detail

    @pytest.mark.asyncio
    async def test_critique_result_passes(self, supervisor):
        output = {"result": "something", "worker_id": "w1"}
        critique = await supervisor.critique_result(Task(task_id="t1", description="x"), output)
        assert critique["is_passed"] is True
        assert critique["score"] == 1.0

    @pytest.mark.asyncio
    async def test_critique_result_no_result(self, supervisor):
        output = {"worker_id": "w1"}
        critique = await supervisor.critique_result(Task(task_id="t1", description="x"), output)
        assert critique["is_passed"] is False

    @pytest.mark.asyncio
    async def test_critique_result_with_error(self, supervisor):
        output = {"result": "partial", "error": "timeout", "worker_id": "w1"}
        critique = await supervisor.critique_result(Task(task_id="t1", description="x"), output)
        assert critique["is_passed"] is False
        assert critique["score"] == 0.3

    @pytest.mark.asyncio
    async def test_critique_updates_performance_score(self, supervisor):
        output = {"result": "ok", "worker_id": "w1"}
        before = supervisor.worker_capabilities["w1"].performance_score
        await supervisor.critique_result(Task(task_id="t1", description="x"), output)
        after = supervisor.worker_capabilities["w1"].performance_score
        # Score should still be close to 1.0 (alpha=0.1)
        assert after == pytest.approx(0.1 * 1.0 + 0.9 * before, abs=0.01)

    @pytest.mark.asyncio
    async def test_critique_disabled(self):
        sup = SupervisorNode(critique_enabled=False)
        result = await sup.critique_result(Task(task_id="t", description="x"), {})
        assert result["is_passed"] is True

    def test_get_next_task_and_has_more(self, supervisor):
        supervisor.plan = [
            Task(task_id="t0", description="a"),
            Task(task_id="t1", description="b"),
        ]
        supervisor.plan_index = 0
        assert supervisor.has_more_tasks() is True
        t = supervisor.get_next_task()
        assert t.task_id == "t0"
        t2 = supervisor.get_next_task()
        assert t2.task_id == "t1"
        assert supervisor.has_more_tasks() is False
        assert supervisor.get_next_task() is None


# ---------------------------------------------------------------------------
# WorkerNode
# ---------------------------------------------------------------------------


class TestWorkerNode:
    @pytest.mark.asyncio
    async def test_execute_task_success(self):
        worker = WorkerNode("w1", ["generic"])
        task = Task(task_id="t1", description="do something")
        result = await worker.execute_task(task)
        assert result["status"] == "completed"
        assert result["worker_id"] == "w1"
        assert task.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_task_at_capacity_raises(self):
        worker = WorkerNode("w1", ["generic"], capacity=1)
        worker.current_tasks.add("existing")
        task = Task(task_id="t2", description="overflow")
        with pytest.raises(RuntimeError, match="at capacity"):
            await worker.execute_task(task)

    @pytest.mark.asyncio
    async def test_task_removed_from_current_after_execution(self):
        worker = WorkerNode("w1", ["generic"], capacity=2)
        task = Task(task_id="t1", description="quick")
        await worker.execute_task(task)
        assert "t1" not in worker.current_tasks
        assert worker.status == NodeStatus.IDLE


# ---------------------------------------------------------------------------
# HierarchicalOrchestrator
# ---------------------------------------------------------------------------


class TestHierarchicalOrchestrator:
    @pytest.fixture()
    def orchestrator(self):
        supervisor = SupervisorNode(require_handoff_contract=False)
        orch = HierarchicalOrchestrator(supervisor=supervisor)
        orch.register_worker(WorkerNode("w1", ["generic"], capacity=5))
        return orch

    @pytest.mark.asyncio
    async def test_execute_goal_single_step(self, orchestrator):
        result = await orchestrator.execute_goal("simple goal", {})
        assert result["goal"] == "simple goal"
        assert result["total_tasks"] == 1
        assert result["completed_tasks"] >= 1

    @pytest.mark.asyncio
    async def test_execute_goal_multiple_steps(self, orchestrator):
        result = await orchestrator.execute_goal(
            "multi step", {"steps": ["step1", "step2", "step3"]}
        )
        assert result["total_tasks"] == 3

    @pytest.mark.asyncio
    async def test_execute_goal_no_workers(self):
        orch = HierarchicalOrchestrator()
        result = await orch.execute_goal("no workers", {})
        assert result["failed_tasks"] >= 1

    @pytest.mark.asyncio
    async def test_default_supervisor_created(self):
        orch = HierarchicalOrchestrator()
        assert orch.supervisor is not None
        assert isinstance(orch.supervisor, SupervisorNode)

    @pytest.mark.asyncio
    async def test_register_worker_also_registers_in_supervisor(self, orchestrator):
        orchestrator.register_worker(WorkerNode("w2", ["analysis"]))
        assert "w2" in orchestrator.workers
        assert "w2" in orchestrator.supervisor.worker_capabilities
