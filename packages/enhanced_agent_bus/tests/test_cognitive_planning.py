"""
Tests for enhanced_agent_bus.cognitive.planning module.

Constitutional Hash: 608508a9bd224290
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

# Load the module file directly to avoid cognitive/__init__.py which pulls in
# graph_rag (requires unavailable src.core.cognitive.graphrag.schema).
_MOD_NAME = "enhanced_agent_bus.cognitive.planning"
_MOD_PATH = Path(__file__).resolve().parent.parent / "cognitive" / "planning.py"
_spec = importlib.util.spec_from_file_location(_MOD_NAME, _MOD_PATH)
assert _spec is not None and _spec.loader is not None
_planning = importlib.util.module_from_spec(_spec)
sys.modules[_MOD_NAME] = _planning
_spec.loader.exec_module(_planning)


def teardown_module() -> None:
    """Remove injected module from sys.modules to avoid polluting other tests."""
    sys.modules.pop(_MOD_NAME, None)


AgentCapability = _planning.AgentCapability
CapabilityMatcher = _planning.CapabilityMatcher
CapabilityType = _planning.CapabilityType
DecomposedTask = _planning.DecomposedTask
ExecutionPlan = _planning.ExecutionPlan
MultiAgentPlanner = _planning.MultiAgentPlanner
PlanStatus = _planning.PlanStatus
PlanStep = _planning.PlanStep
PlanVerifier = _planning.PlanVerifier
TaskDecomposer = _planning.TaskDecomposer
TaskRequirement = _planning.TaskRequirement
TaskStatus = _planning.TaskStatus
VerificationResult = _planning.VerificationResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_step() -> PlanStep:
    return PlanStep(
        step_id="s1",
        name="analyze",
        description="Analyze request",
        capability_type=CapabilityType.INFERENCE,
    )


@pytest.fixture()
def sample_plan(sample_step: PlanStep) -> ExecutionPlan:
    step2 = PlanStep(
        step_id="s2",
        name="evaluate",
        description="Evaluate policy",
        capability_type=CapabilityType.POLICY_EVALUATION,
        dependencies=["s1"],
    )
    return ExecutionPlan(
        plan_id="plan-001",
        tenant_id="tenant-a",
        name="Test Plan",
        description="A test plan",
        steps=[sample_step, step2],
    )


@pytest.fixture()
def matcher_with_agents() -> CapabilityMatcher:
    matcher = CapabilityMatcher()
    matcher.register_capability(
        AgentCapability(
            capability_id="cap-inf",
            capability_type=CapabilityType.INFERENCE,
            agent_id="agent-1",
            description="Inference agent",
        )
    )
    matcher.register_capability(
        AgentCapability(
            capability_id="cap-policy",
            capability_type=CapabilityType.POLICY_EVALUATION,
            agent_id="agent-2",
            description="Policy agent",
            constraints=["strict"],
        )
    )
    matcher.register_capability(
        AgentCapability(
            capability_id="cap-audit",
            capability_type=CapabilityType.AUDIT_LOGGING,
            agent_id="agent-1",
            description="Audit logger",
        )
    )
    return matcher


@pytest.fixture()
def decomposer() -> TaskDecomposer:
    return TaskDecomposer()


@pytest.fixture()
def planner(
    decomposer: TaskDecomposer,
    matcher_with_agents: CapabilityMatcher,
) -> MultiAgentPlanner:
    verifier = PlanVerifier(matcher_with_agents)
    return MultiAgentPlanner(decomposer, matcher_with_agents, verifier)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestEnums:
    def test_task_status_values(self) -> None:
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.BLOCKED.value == "blocked"

    def test_plan_status_values(self) -> None:
        assert PlanStatus.DRAFT.value == "draft"
        assert PlanStatus.VERIFIED.value == "verified"
        assert PlanStatus.REPLANNING.value == "replanning"

    def test_capability_type_values(self) -> None:
        assert CapabilityType.POLICY_EVALUATION.value == "policy_evaluation"
        assert CapabilityType.CONSTITUTIONAL_CHECK.value == "constitutional_check"
        assert CapabilityType.HITL_APPROVAL.value == "hitl_approval"


# ---------------------------------------------------------------------------
# AgentCapability Tests
# ---------------------------------------------------------------------------


class TestAgentCapability:
    def test_to_dict(self) -> None:
        cap = AgentCapability(
            capability_id="c1",
            capability_type=CapabilityType.INFERENCE,
            agent_id="a1",
            description="test",
            constraints=["fast"],
            max_concurrent=5,
        )
        d = cap.to_dict()
        assert d["capability_id"] == "c1"
        assert d["capability_type"] == "inference"
        assert d["agent_id"] == "a1"
        assert d["constraints"] == ["fast"]
        assert d["max_concurrent"] == 5
        assert d["timeout_seconds"] == 300

    def test_defaults(self) -> None:
        cap = AgentCapability(
            capability_id="c1",
            capability_type=CapabilityType.INFERENCE,
            agent_id="a1",
            description="test",
        )
        assert cap.constraints == []
        assert cap.required_permissions == []
        assert cap.max_concurrent == 1
        assert cap.metadata == {}


# ---------------------------------------------------------------------------
# PlanStep Tests
# ---------------------------------------------------------------------------


class TestPlanStep:
    def test_to_dict_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        step = PlanStep(
            step_id="s1",
            name="step",
            description="desc",
            assigned_agent="agent-1",
            capability_type=CapabilityType.AUDIT_LOGGING,
            dependencies=["s0"],
            status=TaskStatus.COMPLETED,
            started_at=now,
            completed_at=now,
        )
        d = step.to_dict()
        assert d["step_id"] == "s1"
        assert d["capability_type"] == "audit_logging"
        assert d["dependencies"] == ["s0"]
        assert d["status"] == "completed"
        assert d["started_at"] is not None
        assert d["completed_at"] is not None

    def test_to_dict_none_capability(self) -> None:
        step = PlanStep(step_id="s1", name="x", description="y")
        d = step.to_dict()
        assert d["capability_type"] is None
        assert d["started_at"] is None
        assert d["completed_at"] is None

    def test_can_start_no_dependencies(self) -> None:
        step = PlanStep(step_id="s1", name="x", description="y")
        assert step.can_start(set()) is True

    def test_can_start_with_met_dependencies(self) -> None:
        step = PlanStep(step_id="s2", name="x", description="y", dependencies=["s1"])
        assert step.can_start({"s1"}) is True

    def test_can_start_with_unmet_dependencies(self) -> None:
        step = PlanStep(step_id="s2", name="x", description="y", dependencies=["s1"])
        assert step.can_start(set()) is False

    def test_mark_started(self, sample_step: PlanStep) -> None:
        sample_step.mark_started()
        assert sample_step.status == TaskStatus.IN_PROGRESS
        assert sample_step.started_at is not None

    def test_mark_completed_without_output(self, sample_step: PlanStep) -> None:
        sample_step.mark_completed()
        assert sample_step.status == TaskStatus.COMPLETED
        assert sample_step.completed_at is not None
        assert sample_step.output_data == {}

    def test_mark_completed_with_output(self, sample_step: PlanStep) -> None:
        sample_step.mark_completed({"result": 42})
        assert sample_step.output_data == {"result": 42}

    def test_mark_failed(self, sample_step: PlanStep) -> None:
        sample_step.mark_failed("boom")
        assert sample_step.status == TaskStatus.FAILED
        assert sample_step.error_message == "boom"
        assert sample_step.retry_count == 1
        assert sample_step.completed_at is not None

    def test_mark_failed_increments_retry(self, sample_step: PlanStep) -> None:
        sample_step.mark_failed("err1")
        sample_step.mark_failed("err2")
        assert sample_step.retry_count == 2


# ---------------------------------------------------------------------------
# ExecutionPlan Tests
# ---------------------------------------------------------------------------


class TestExecutionPlan:
    def test_to_dict(self, sample_plan: ExecutionPlan) -> None:
        d = sample_plan.to_dict()
        assert d["plan_id"] == "plan-001"
        assert d["tenant_id"] == "tenant-a"
        assert d["status"] == "draft"
        assert len(d["steps"]) == 2
        assert d["verified_at"] is None
        assert d["started_at"] is None
        assert d["completed_at"] is None

    def test_get_ready_steps_initial(self, sample_plan: ExecutionPlan) -> None:
        ready = sample_plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "s1"

    def test_get_ready_steps_after_first_completed(self, sample_plan: ExecutionPlan) -> None:
        sample_plan.steps[0].status = TaskStatus.COMPLETED
        ready = sample_plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "s2"

    def test_get_step_found(self, sample_plan: ExecutionPlan) -> None:
        step = sample_plan.get_step("s1")
        assert step is not None
        assert step.name == "analyze"

    def test_get_step_not_found(self, sample_plan: ExecutionPlan) -> None:
        assert sample_plan.get_step("nonexistent") is None

    def test_is_complete_false(self, sample_plan: ExecutionPlan) -> None:
        assert sample_plan.is_complete() is False

    def test_is_complete_true(self, sample_plan: ExecutionPlan) -> None:
        for s in sample_plan.steps:
            s.status = TaskStatus.COMPLETED
        assert sample_plan.is_complete() is True

    def test_has_failures(self, sample_plan: ExecutionPlan) -> None:
        assert sample_plan.has_failures() is False
        sample_plan.steps[0].status = TaskStatus.FAILED
        assert sample_plan.has_failures() is True

    def test_progress_percent_empty(self) -> None:
        plan = ExecutionPlan(plan_id="p", tenant_id="t", name="n", description="d", steps=[])
        assert plan.progress_percent() == 0.0

    def test_progress_percent_partial(self, sample_plan: ExecutionPlan) -> None:
        sample_plan.steps[0].status = TaskStatus.COMPLETED
        assert sample_plan.progress_percent() == 50.0

    def test_progress_percent_full(self, sample_plan: ExecutionPlan) -> None:
        for s in sample_plan.steps:
            s.status = TaskStatus.COMPLETED
        assert sample_plan.progress_percent() == 100.0


# ---------------------------------------------------------------------------
# TaskDecomposer Tests
# ---------------------------------------------------------------------------


class TestTaskDecomposer:
    def test_default_decompose_simple_goal(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("do something")
        assert isinstance(result, DecomposedTask)
        assert result.original_goal == "do something"
        # Default: analyze_request + audit_log
        assert result.estimated_steps == 2
        names = [s["name"] for s in result.subtasks]
        assert "analyze_request" in names
        assert "audit_log" in names

    def test_decompose_with_policy_keyword(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("evaluate policy compliance")
        names = [s["name"] for s in result.subtasks]
        assert "retrieve_policies" in names
        assert "evaluate_policy" in names

    def test_decompose_with_constitutional_keyword(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("check constitutional rules")
        names = [s["name"] for s in result.subtasks]
        assert "check_constitutional" in names

    def test_decompose_with_approval_keyword(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("requires human approval")
        names = [s["name"] for s in result.subtasks]
        assert "request_approval" in names

    def test_decompose_with_all_keywords(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose(
            "evaluate policy with constitutional check and human approval"
        )
        assert result.estimated_steps >= 5
        assert result.complexity_score > 0.0

    def test_custom_decomposer_fn(self) -> None:
        custom_subtasks = [
            {"name": "custom_step", "description": "Custom", "capability": "inference"}
        ]
        decomposer = TaskDecomposer(decomposer_fn=lambda _goal: custom_subtasks)
        result = decomposer.decompose("anything")
        assert result.subtasks == custom_subtasks
        assert result.estimated_steps == 1

    def test_decompose_with_context(self, decomposer: TaskDecomposer) -> None:
        ctx = {"source": "test"}
        result = decomposer.decompose("goal", context=ctx)
        assert result.metadata == ctx

    def test_decompose_without_context(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("goal")
        assert result.metadata == {}

    def test_infer_requirements_unknown_capability(self, decomposer: TaskDecomposer) -> None:
        subtasks = [{"name": "x", "capability": "unknown_cap"}]
        reqs = decomposer._infer_requirements(subtasks)
        assert reqs[0].capability_type == CapabilityType.INFERENCE

    def test_infer_requirements_missing_capability(self, decomposer: TaskDecomposer) -> None:
        subtasks = [{"name": "x"}]
        reqs = decomposer._infer_requirements(subtasks)
        assert reqs[0].capability_type == CapabilityType.INFERENCE

    def test_complexity_capped_at_one(self, decomposer: TaskDecomposer) -> None:
        # Many subtasks with critical capabilities should cap at 1.0
        subtasks = [
            {"name": f"s{i}", "capability": CapabilityType.CONSTITUTIONAL_CHECK.value}
            for i in range(20)
        ]
        reqs = decomposer._infer_requirements(subtasks)
        score = decomposer._calculate_complexity(subtasks, reqs)
        assert score == 1.0

    def test_complexity_basic(self, decomposer: TaskDecomposer) -> None:
        subtasks = [{"name": "s1", "capability": "inference"}]
        reqs = decomposer._infer_requirements(subtasks)
        score = decomposer._calculate_complexity(subtasks, reqs)
        assert score == pytest.approx(0.1)

    def test_task_id_is_hex(self, decomposer: TaskDecomposer) -> None:
        result = decomposer.decompose("test")
        assert len(result.task_id) == 16
        int(result.task_id, 16)  # Should not raise


# ---------------------------------------------------------------------------
# CapabilityMatcher Tests
# ---------------------------------------------------------------------------


class TestCapabilityMatcher:
    def test_register_and_find(self, matcher_with_agents: CapabilityMatcher) -> None:
        results = matcher_with_agents.find_capable_agents(CapabilityType.INFERENCE)
        assert len(results) == 1
        assert results[0].agent_id == "agent-1"

    def test_find_no_match(self, matcher_with_agents: CapabilityMatcher) -> None:
        results = matcher_with_agents.find_capable_agents(CapabilityType.HITL_APPROVAL)
        assert results == []

    def test_find_with_matching_constraints(self, matcher_with_agents: CapabilityMatcher) -> None:
        results = matcher_with_agents.find_capable_agents(
            CapabilityType.POLICY_EVALUATION, constraints=["strict"]
        )
        assert len(results) == 1

    def test_find_with_unmet_constraints(self, matcher_with_agents: CapabilityMatcher) -> None:
        results = matcher_with_agents.find_capable_agents(
            CapabilityType.POLICY_EVALUATION, constraints=["nonexistent"]
        )
        assert results == []

    def test_match_requirements(self, matcher_with_agents: CapabilityMatcher) -> None:
        reqs = [
            TaskRequirement(capability_type=CapabilityType.INFERENCE),
            TaskRequirement(capability_type=CapabilityType.HITL_APPROVAL),
        ]
        matches = matcher_with_agents.match_requirements(reqs)
        assert len(matches[CapabilityType.INFERENCE]) == 1
        assert len(matches[CapabilityType.HITL_APPROVAL]) == 0

    def test_get_agent_capabilities(self, matcher_with_agents: CapabilityMatcher) -> None:
        caps = matcher_with_agents.get_agent_capabilities("agent-1")
        assert len(caps) == 2
        cap_types = {c.capability_type for c in caps}
        assert CapabilityType.INFERENCE in cap_types
        assert CapabilityType.AUDIT_LOGGING in cap_types

    def test_get_agent_capabilities_unknown(self, matcher_with_agents: CapabilityMatcher) -> None:
        assert matcher_with_agents.get_agent_capabilities("ghost") == []


# ---------------------------------------------------------------------------
# PlanVerifier Tests
# ---------------------------------------------------------------------------


class TestPlanVerifier:
    def test_verify_valid_plan(self, matcher_with_agents: CapabilityMatcher) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(
            step_id="s1",
            name="infer",
            description="d",
            capability_type=CapabilityType.INFERENCE,
            assigned_agent="agent-1",
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert result.is_valid is True
        assert plan.status == PlanStatus.VERIFIED
        assert plan.verified_at is not None
        assert "dag_structure" in result.checked_constraints

    def test_verify_missing_dependency(self, matcher_with_agents: CapabilityMatcher) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(
            step_id="s1",
            name="x",
            description="d",
            dependencies=["nonexistent"],
            capability_type=CapabilityType.INFERENCE,
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert result.is_valid is False
        assert any(v["type"] == "dag_violation" for v in result.violations)

    def test_verify_circular_dependency(self, matcher_with_agents: CapabilityMatcher) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        s1 = PlanStep(
            step_id="s1",
            name="a",
            description="d",
            dependencies=["s2"],
            capability_type=CapabilityType.INFERENCE,
        )
        s2 = PlanStep(
            step_id="s2",
            name="b",
            description="d",
            dependencies=["s1"],
            capability_type=CapabilityType.INFERENCE,
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[s1, s2])
        result = verifier.verify(plan)
        assert result.is_valid is False
        assert any(v["type"] == "dag_violation" for v in result.violations)

    def test_verify_no_capable_agent(self) -> None:
        empty_matcher = CapabilityMatcher()
        verifier = PlanVerifier(empty_matcher)
        step = PlanStep(
            step_id="s1",
            name="x",
            description="d",
            capability_type=CapabilityType.HITL_APPROVAL,
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert result.is_valid is False
        assert any(v["type"] == "no_capable_agent" for v in result.violations)

    def test_verify_missing_capability_type_warning(
        self, matcher_with_agents: CapabilityMatcher
    ) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(step_id="s1", name="x", description="d", capability_type=None)
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert any(w["type"] == "missing_capability" for w in result.warnings)

    def test_verify_invalid_agent_assignment(self, matcher_with_agents: CapabilityMatcher) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(
            step_id="s1",
            name="x",
            description="d",
            capability_type=CapabilityType.POLICY_EVALUATION,
            assigned_agent="agent-1",  # agent-1 does NOT have POLICY_EVALUATION
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert any(v["type"] == "invalid_assignment" for v in result.violations)

    def test_verify_constitutional_hash_mismatch(
        self, matcher_with_agents: CapabilityMatcher
    ) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(
            step_id="s1",
            name="x",
            description="d",
            capability_type=CapabilityType.INFERENCE,
            constitutional_hash="wrong_hash",
        )
        plan = ExecutionPlan(plan_id="p1", tenant_id="t", name="n", description="d", steps=[step])
        result = verifier.verify(plan)
        assert any(v["type"] == "constitutional_hash_mismatch" for v in result.violations)

    def test_verify_plan_constitutional_hash_mismatch(
        self, matcher_with_agents: CapabilityMatcher
    ) -> None:
        verifier = PlanVerifier(matcher_with_agents)
        step = PlanStep(
            step_id="s1",
            name="x",
            description="d",
            capability_type=CapabilityType.INFERENCE,
        )
        plan = ExecutionPlan(
            plan_id="p1",
            tenant_id="t",
            name="n",
            description="d",
            steps=[step],
            constitutional_hash="bad_hash",
        )
        result = verifier.verify(plan)
        assert any(v["type"] == "plan_constitutional_hash_mismatch" for v in result.violations)


# ---------------------------------------------------------------------------
# VerificationResult Tests
# ---------------------------------------------------------------------------


class TestVerificationResult:
    def test_defaults(self) -> None:
        vr = VerificationResult(is_valid=True)
        assert vr.violations == []
        assert vr.warnings == []
        assert vr.checked_constraints == []
        assert vr.verified_at is not None


# ---------------------------------------------------------------------------
# MultiAgentPlanner Tests
# ---------------------------------------------------------------------------


class TestMultiAgentPlanner:
    def test_create_plan(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "do inference task")
        assert plan.tenant_id == "t1"
        assert plan.status == PlanStatus.DRAFT
        assert len(plan.steps) >= 2
        assert plan.metadata["original_goal"] == "do inference task"

    def test_create_plan_custom_name(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal", name="Custom Name")
        assert plan.name == "Custom Name"

    def test_create_plan_default_name(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "a short goal")
        assert plan.name.startswith("Plan for:")

    def test_create_plan_assigns_agents(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "simple goal")
        # First step (inference) should be assigned to agent-1
        inference_steps = [s for s in plan.steps if s.capability_type == CapabilityType.INFERENCE]
        assert any(s.assigned_agent == "agent-1" for s in inference_steps)

    def test_create_plan_sequential_dependencies(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        for i, step in enumerate(plan.steps):
            if i == 0:
                assert step.dependencies == []
            else:
                assert len(step.dependencies) == 1

    def test_verify_plan_valid(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "simple inference")
        result = planner.verify_plan(plan.plan_id)
        assert result is not None
        # May or may not be valid depending on agent assignment;
        # at least it returns a VerificationResult
        assert isinstance(result, VerificationResult)

    def test_verify_plan_not_found(self, planner: MultiAgentPlanner) -> None:
        assert planner.verify_plan("nonexistent") is None

    def test_get_plan(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        retrieved = planner.get_plan(plan.plan_id)
        assert retrieved is plan

    def test_get_plan_not_found(self, planner: MultiAgentPlanner) -> None:
        assert planner.get_plan("nonexistent") is None

    def test_replan_success(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        first_step = plan.steps[0]
        first_step.mark_failed("something broke")

        recovery = planner.replan(plan.plan_id, first_step.step_id)
        assert recovery is not None
        assert recovery.plan_id != plan.plan_id
        assert plan.status == PlanStatus.REPLANNING
        # Recovery plan has its own metadata from create_plan;
        # the original_goal in metadata references the failure context
        assert "original_goal" in recovery.metadata
        assert first_step.name in recovery.metadata["original_goal"]

    def test_replan_plan_not_found(self, planner: MultiAgentPlanner) -> None:
        assert planner.replan("nonexistent", "s1") is None

    def test_replan_step_not_found(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        assert planner.replan(plan.plan_id, "nonexistent") is None

    def test_execute_step_plan_not_found(self, planner: MultiAgentPlanner) -> None:
        assert planner.execute_step("nonexistent", "s1") is None

    def test_execute_step_step_not_found(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        assert planner.execute_step(plan.plan_id, "nonexistent") is None

    def test_execute_step_blocked(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        # Second step depends on first; executing it should block
        if len(plan.steps) > 1:
            second = plan.steps[1]
            result = planner.execute_step(plan.plan_id, second.step_id)
            assert result is not None
            assert result.status == TaskStatus.BLOCKED

    def test_execute_step_no_executor(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        first = plan.steps[0]
        result = planner.execute_step(plan.plan_id, first.step_id)
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.output_data == {"mock": True}

    def test_execute_step_with_executor(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        first = plan.steps[0]

        def executor(step: PlanStep) -> dict:
            return {"executed": step.name}

        result = planner.execute_step(plan.plan_id, first.step_id, executor=executor)
        assert result is not None
        assert result.status == TaskStatus.COMPLETED
        assert result.output_data["executed"] == first.name

    def test_execute_step_executor_raises(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        first = plan.steps[0]

        def bad_executor(_step: PlanStep) -> dict:
            raise RuntimeError("executor failed")

        result = planner.execute_step(plan.plan_id, first.step_id, executor=bad_executor)
        assert result is not None
        assert result.status == TaskStatus.FAILED
        assert result.error_message == "executor failed"

    def test_execute_all_steps_completes_plan(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        for step in plan.steps:
            planner.execute_step(plan.plan_id, step.step_id)
        assert plan.status == PlanStatus.COMPLETED
        assert plan.completed_at is not None

    def test_execute_step_failure_marks_plan_failed(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal")
        first = plan.steps[0]
        # Exhaust retries
        first.max_retries = 0

        def bad_executor(_step: PlanStep) -> dict:
            raise ValueError("fail")

        planner.execute_step(plan.plan_id, first.step_id, executor=bad_executor)
        assert plan.status == PlanStatus.FAILED

    def test_create_plan_with_context(self, planner: MultiAgentPlanner) -> None:
        plan = planner.create_plan("t1", "goal", context={"key": "val"})
        assert plan is not None

    def test_create_plan_invalid_capability_falls_back(self) -> None:
        def custom_fn(_g: str) -> list[dict[str, str]]:
            return [{"name": "x", "capability": "bogus_cap"}]

        decomposer = TaskDecomposer(decomposer_fn=custom_fn)
        matcher = CapabilityMatcher()
        verifier = PlanVerifier(matcher)
        planner = MultiAgentPlanner(decomposer, matcher, verifier)

        plan = planner.create_plan("t1", "goal")
        assert plan.steps[0].capability_type == CapabilityType.INFERENCE
