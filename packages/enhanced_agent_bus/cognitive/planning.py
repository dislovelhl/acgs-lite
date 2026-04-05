try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

"""
Multi-Agent Planning - Task decomposition, capability matching, and plan verification.

Constitutional Hash: 608508a9bd224290
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

PLAN_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
)


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class PlanStatus(Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REPLANNING = "replanning"


class CapabilityType(Enum):
    POLICY_EVALUATION = "policy_evaluation"
    PRINCIPLE_SYNTHESIS = "principle_synthesis"
    CONSTITUTIONAL_CHECK = "constitutional_check"
    HITL_APPROVAL = "hitl_approval"
    AUDIT_LOGGING = "audit_logging"
    DATA_RETRIEVAL = "data_retrieval"
    GRAPH_QUERY = "graph_query"
    INFERENCE = "inference"
    TOOL_EXECUTION = "tool_execution"


@dataclass
class AgentCapability:
    capability_id: str
    capability_type: CapabilityType
    agent_id: str
    description: str
    constraints: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    max_concurrent: int = 1
    timeout_seconds: int = 300
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH  # pragma: allowlist secret

    def to_dict(self) -> JSONDict:
        return {
            "capability_id": self.capability_id,
            "capability_type": self.capability_type.value,
            "agent_id": self.agent_id,
            "description": self.description,
            "constraints": self.constraints,
            "required_permissions": self.required_permissions,
            "max_concurrent": self.max_concurrent,
            "timeout_seconds": self.timeout_seconds,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }


@dataclass
class TaskRequirement:
    capability_type: CapabilityType
    priority: int = 1
    required: bool = True
    constraints: list[str] = field(default_factory=list)


@dataclass
class PlanStep:
    step_id: str
    name: str
    description: str
    assigned_agent: str | None = None
    capability_type: CapabilityType | None = None
    dependencies: list[str] = field(default_factory=list)
    input_data: JSONDict = field(default_factory=dict)
    output_data: JSONDict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "description": self.description,
            "assigned_agent": self.assigned_agent,
            "capability_type": self.capability_type.value if self.capability_type else None,
            "dependencies": self.dependencies,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "constitutional_hash": self.constitutional_hash,
        }

    def can_start(self, completed_steps: set[str]) -> bool:
        return all(dep in completed_steps for dep in self.dependencies)

    def mark_started(self) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.now(UTC)

    def mark_completed(self, output: JSONDict | None = None) -> None:
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(UTC)
        if output:
            self.output_data = output

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now(UTC)
        self.error_message = error
        self.retry_count += 1


@dataclass
class ExecutionPlan:
    plan_id: str
    tenant_id: str
    name: str
    description: str
    steps: list[PlanStep]
    status: PlanStatus = PlanStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    verified_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    verification_result: JSONDict | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH

    def to_dict(self) -> JSONDict:
        return {
            "plan_id": self.plan_id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "verification_result": self.verification_result,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
        }

    def get_ready_steps(self) -> list[PlanStep]:
        completed = {s.step_id for s in self.steps if s.status == TaskStatus.COMPLETED}
        return [s for s in self.steps if s.status == TaskStatus.PENDING and s.can_start(completed)]

    def get_step(self, step_id: str) -> PlanStep | None:
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def is_complete(self) -> bool:
        return all(s.status == TaskStatus.COMPLETED for s in self.steps)

    def has_failures(self) -> bool:
        return any(s.status == TaskStatus.FAILED for s in self.steps)

    def progress_percent(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == TaskStatus.COMPLETED)
        return (completed / len(self.steps)) * 100


@dataclass
class DecomposedTask:
    task_id: str
    original_goal: str
    subtasks: list[JSONDict]
    requirements: list[TaskRequirement]
    estimated_steps: int
    complexity_score: float
    metadata: JSONDict = field(default_factory=dict)


class TaskDecomposer:
    def __init__(self, decomposer_fn: Callable[[str], list[JSONDict]] | None = None) -> None:
        self._decomposer_fn = decomposer_fn

    def decompose(self, goal: str, context: JSONDict | None = None) -> DecomposedTask:
        task_id = hashlib.sha256(f"{goal}:{datetime.now(UTC).isoformat()}".encode()).hexdigest()[
            :16
        ]

        if self._decomposer_fn:
            subtasks = self._decomposer_fn(goal)
        else:
            subtasks = self._default_decompose(goal)

        requirements = self._infer_requirements(subtasks)
        complexity = self._calculate_complexity(subtasks, requirements)

        return DecomposedTask(
            task_id=task_id,
            original_goal=goal,
            subtasks=subtasks,
            requirements=requirements,
            estimated_steps=len(subtasks),
            complexity_score=complexity,
            metadata=context or {},
        )

    def _default_decompose(self, goal: str) -> list[JSONDict]:
        goal_lower = goal.lower()

        subtasks = [
            {
                "name": "analyze_request",
                "description": f"Analyze the goal: {goal}",
                "capability": CapabilityType.INFERENCE.value,
            }
        ]

        if "policy" in goal_lower or "evaluate" in goal_lower:
            subtasks.append(
                {
                    "name": "retrieve_policies",
                    "description": "Retrieve relevant policies from governance graph",
                    "capability": CapabilityType.GRAPH_QUERY.value,
                }
            )
            subtasks.append(
                {
                    "name": "evaluate_policy",
                    "description": "Evaluate policy compliance",
                    "capability": CapabilityType.POLICY_EVALUATION.value,
                }
            )

        if "constitutional" in goal_lower or "principle" in goal_lower:
            subtasks.append(
                {
                    "name": "check_constitutional",
                    "description": "Verify constitutional compliance",
                    "capability": CapabilityType.CONSTITUTIONAL_CHECK.value,
                }
            )

        if "approval" in goal_lower or "human" in goal_lower:
            subtasks.append(
                {
                    "name": "request_approval",
                    "description": "Request human-in-the-loop approval",
                    "capability": CapabilityType.HITL_APPROVAL.value,
                }
            )

        subtasks.append(
            {
                "name": "audit_log",
                "description": "Log the operation to audit trail",
                "capability": CapabilityType.AUDIT_LOGGING.value,
            }
        )

        return subtasks

    def _infer_requirements(self, subtasks: list[JSONDict]) -> list[TaskRequirement]:
        requirements = []
        for subtask in subtasks:
            cap_str = subtask.get("capability", CapabilityType.INFERENCE.value)
            try:
                cap_type = CapabilityType(cap_str)
            except ValueError:
                cap_type = CapabilityType.INFERENCE

            requirements.append(
                TaskRequirement(
                    capability_type=cap_type,
                    priority=1,
                    required=True,
                )
            )
        return requirements

    def _calculate_complexity(
        self, subtasks: list[JSONDict], requirements: list[TaskRequirement]
    ) -> float:
        base = len(subtasks) * 0.1

        critical_caps = {
            CapabilityType.CONSTITUTIONAL_CHECK,
            CapabilityType.HITL_APPROVAL,
            CapabilityType.POLICY_EVALUATION,
        }
        critical_count = sum(1 for r in requirements if r.capability_type in critical_caps)
        base += critical_count * 0.2

        return min(base, 1.0)


class CapabilityMatcher:
    def __init__(self) -> None:
        self._capabilities: dict[str, AgentCapability] = {}
        self._agent_capabilities: dict[str, list[str]] = {}

    def register_capability(self, capability: AgentCapability) -> None:
        self._capabilities[capability.capability_id] = capability

        if capability.agent_id not in self._agent_capabilities:
            self._agent_capabilities[capability.agent_id] = []
        self._agent_capabilities[capability.agent_id].append(capability.capability_id)

    def find_capable_agents(
        self,
        capability_type: CapabilityType,
        constraints: list[str] | None = None,
    ) -> list[AgentCapability]:
        matches = []

        for cap in self._capabilities.values():
            if cap.capability_type != capability_type:
                continue

            if constraints:
                if not all(c in cap.constraints for c in constraints):
                    continue

            matches.append(cap)

        return matches

    def match_requirements(
        self, requirements: list[TaskRequirement]
    ) -> dict[CapabilityType, list[AgentCapability]]:
        matches: dict[CapabilityType, list[AgentCapability]] = {}

        for req in requirements:
            capable = self.find_capable_agents(req.capability_type, req.constraints)
            matches[req.capability_type] = capable

        return matches

    def get_agent_capabilities(self, agent_id: str) -> list[AgentCapability]:
        cap_ids = self._agent_capabilities.get(agent_id, [])
        return [self._capabilities[cid] for cid in cap_ids if cid in self._capabilities]


@dataclass
class VerificationResult:
    is_valid: bool
    violations: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    checked_constraints: list[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PolicyEvaluator(Protocol):
    def evaluate(self, policy_id: str, context: JSONDict) -> bool: ...


class PlanVerifier:
    def __init__(
        self,
        capability_matcher: CapabilityMatcher,
        policy_evaluator: PolicyEvaluator | None = None,
    ):
        self._matcher = capability_matcher
        self._policy_evaluator = policy_evaluator

    def verify(self, plan: ExecutionPlan) -> VerificationResult:
        violations: list[dict] = []
        warnings: list[dict] = []
        checked: list[str] = []

        dag_result = self._verify_dag(plan)
        checked.append("dag_structure")
        if not dag_result[0]:
            violations.append({"type": "dag_violation", "message": dag_result[1]})

        cap_result = self._verify_capabilities(plan)
        checked.append("capability_assignment")
        violations.extend(cap_result[0])
        warnings.extend(cap_result[1])

        const_result = self._verify_constitutional(plan)
        checked.append("constitutional_compliance")
        violations.extend(const_result)

        is_valid = len(violations) == 0

        result = VerificationResult(
            is_valid=is_valid,
            violations=violations,
            warnings=warnings,
            checked_constraints=checked,
        )

        if is_valid:
            plan.status = PlanStatus.VERIFIED
            plan.verified_at = datetime.now(UTC)
            plan.verification_result = {
                "is_valid": True,
                "warnings": warnings,
                "checked": checked,
            }

        return result

    def _verify_dag(self, plan: ExecutionPlan) -> tuple[bool, str]:
        """Verify that the plan forms a valid directed acyclic graph (DAG)."""
        # Check dependency references exist
        dependency_check = self._verify_dependencies_exist(plan)
        if not dependency_check[0]:
            return dependency_check

        # Check for circular dependencies
        cycle_check = self._detect_cycles(plan)
        if not cycle_check[0]:
            return cycle_check

        return True, ""

    def _verify_dependencies_exist(self, plan: ExecutionPlan) -> tuple[bool, str]:
        """Verify all step dependencies reference existing steps."""
        step_ids = {s.step_id for s in plan.steps}

        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    return False, f"Step {step.step_id} depends on unknown step {dep}"

        return True, ""

    def _detect_cycles(self, plan: ExecutionPlan) -> tuple[bool, str]:
        """Detect circular dependencies using DFS."""
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            step = plan.get_step(step_id)
            if step:
                for dep in step.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(step_id)
            return False

        # Check each unvisited step for cycles
        for step in plan.steps:
            if step.step_id not in visited:
                if has_cycle(step.step_id):
                    return False, "Circular dependency detected"

        return True, ""

    def _verify_capabilities(self, plan: ExecutionPlan) -> tuple[list[JSONDict], list[JSONDict]]:
        violations = []
        warnings = []

        for step in plan.steps:
            if not step.capability_type:
                warnings.append(
                    {
                        "type": "missing_capability",
                        "step_id": step.step_id,
                        "message": f"Step {step.name} has no capability type assigned",
                    }
                )
                continue

            capable = self._matcher.find_capable_agents(step.capability_type)
            if not capable:
                violations.append(
                    {
                        "type": "no_capable_agent",
                        "step_id": step.step_id,
                        "capability": step.capability_type.value,
                        "message": f"No agent can perform {step.capability_type.value}",
                    }
                )

            if step.assigned_agent:
                agent_caps = self._matcher.get_agent_capabilities(step.assigned_agent)
                if not any(c.capability_type == step.capability_type for c in agent_caps):
                    violations.append(
                        {
                            "type": "invalid_assignment",
                            "step_id": step.step_id,
                            "agent_id": step.assigned_agent,
                            "message": f"Agent {step.assigned_agent} cannot perform {step.capability_type.value}",
                        }
                    )

        return violations, warnings

    def _verify_constitutional(self, plan: ExecutionPlan) -> list[JSONDict]:
        violations = []

        for step in plan.steps:
            if step.constitutional_hash != CONSTITUTIONAL_HASH:
                violations.append(
                    {
                        "type": "constitutional_hash_mismatch",
                        "step_id": step.step_id,
                        "expected": CONSTITUTIONAL_HASH,
                        "actual": step.constitutional_hash,
                    }
                )

        if plan.constitutional_hash != CONSTITUTIONAL_HASH:
            violations.append(
                {
                    "type": "plan_constitutional_hash_mismatch",
                    "plan_id": plan.plan_id,
                    "expected": CONSTITUTIONAL_HASH,
                    "actual": plan.constitutional_hash,
                }
            )

        return violations


class MultiAgentPlanner:
    def __init__(
        self,
        decomposer: TaskDecomposer,
        matcher: CapabilityMatcher,
        verifier: PlanVerifier,
    ) -> None:
        self._decomposer = decomposer
        self._matcher = matcher
        self._verifier = verifier
        self._plans: dict[str, ExecutionPlan] = {}

    def create_plan(
        self,
        tenant_id: str,
        goal: str,
        name: str | None = None,
        context: JSONDict | None = None,
    ) -> ExecutionPlan:
        decomposed = self._decomposer.decompose(goal, context)

        plan_id = hashlib.sha256(
            f"{tenant_id}:{goal}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        steps = []
        prev_step_id: str | None = None

        for i, subtask in enumerate(decomposed.subtasks):
            step_id = f"{plan_id}:step:{i}"

            try:
                cap_type = CapabilityType(subtask.get("capability", "inference"))
            except ValueError:
                cap_type = CapabilityType.INFERENCE

            step = PlanStep(
                step_id=step_id,
                name=subtask.get("name", f"step_{i}"),
                description=subtask.get("description", ""),
                capability_type=cap_type,
                dependencies=[prev_step_id] if prev_step_id else [],
            )

            capable = self._matcher.find_capable_agents(cap_type)
            if capable:
                step.assigned_agent = capable[0].agent_id

            steps.append(step)
            prev_step_id = step_id

        plan = ExecutionPlan(
            plan_id=plan_id,
            tenant_id=tenant_id,
            name=name or f"Plan for: {goal[:50]}",
            description=goal,
            steps=steps,
            metadata={
                "complexity": decomposed.complexity_score,
                "original_goal": goal,
            },
        )

        self._plans[plan_id] = plan
        return plan

    def verify_plan(self, plan_id: str) -> VerificationResult | None:
        plan = self._plans.get(plan_id)
        if not plan:
            return None

        return self._verifier.verify(plan)

    def get_plan(self, plan_id: str) -> ExecutionPlan | None:
        return self._plans.get(plan_id)

    def replan(
        self,
        plan_id: str,
        failed_step_id: str,
        error_context: JSONDict | None = None,
    ) -> ExecutionPlan | None:
        original = self._plans.get(plan_id)
        if not original:
            return None

        failed_step = original.get_step(failed_step_id)
        if not failed_step:
            return None

        original.status = PlanStatus.REPLANNING

        new_goal = f"Recover from failure in {failed_step.name}: {failed_step.error_message}"
        recovery_plan = self.create_plan(
            original.tenant_id,
            new_goal,
            name=f"Recovery for {original.name}",
            context={
                "original_plan": plan_id,
                "failed_step": failed_step_id,
                **(error_context or {}),
            },
        )

        return recovery_plan

    def execute_step(
        self,
        plan_id: str,
        step_id: str,
        executor: Callable[[PlanStep], JSONDict] | None = None,
    ) -> PlanStep | None:
        plan = self._plans.get(plan_id)
        if not plan:
            return None

        step = plan.get_step(step_id)
        if not step:
            return None

        completed = {s.step_id for s in plan.steps if s.status == TaskStatus.COMPLETED}
        if not step.can_start(completed):
            step.status = TaskStatus.BLOCKED
            return step

        step.mark_started()

        if executor:
            try:
                result = executor(step)
                step.mark_completed(result)
            except PLAN_EXECUTION_ERRORS as e:
                step.mark_failed(str(e))
        else:
            step.mark_completed({"mock": True})

        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
            plan.completed_at = datetime.now(UTC)
        elif plan.has_failures():
            retryable = [
                s
                for s in plan.steps
                if s.status == TaskStatus.FAILED and s.retry_count < s.max_retries
            ]
            if not retryable:
                plan.status = PlanStatus.FAILED

        return step
