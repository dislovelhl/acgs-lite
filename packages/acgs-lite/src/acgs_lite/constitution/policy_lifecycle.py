"""Policy lifecycle orchestrator — end-to-end state machine for governance policy promotion.

Manages a policy from initial draft through review, staged rollout, active deployment,
and eventual deprecation. Enforces automated gate checks at each transition (minimum
approvals, test suite pass, blast-radius threshold, lint clean), provides staged
percentage rollouts, auto-supersession of older policies, and a full transition
audit trail.

Zero hot-path overhead — all lifecycle management runs offline, independent of the
governance engine's critical evaluation path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyState(str, Enum):
    """Valid lifecycle states for a managed governance policy."""

    DRAFT = "draft"
    REVIEW = "review"
    STAGED = "staged"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class TransitionResult(str, Enum):
    """Outcome of a state transition attempt."""

    SUCCESS = "success"
    BLOCKED_BY_GATE = "blocked_by_gate"
    INVALID_TRANSITION = "invalid_transition"
    POLICY_NOT_FOUND = "policy_not_found"


class GateType(str, Enum):
    """Types of automated gate checks enforced before a transition."""

    MIN_APPROVALS = "min_approvals"
    LINT_CLEAN = "lint_clean"
    TEST_SUITE_PASS = "test_suite_pass"
    BLAST_RADIUS_BELOW = "blast_radius_below"
    ATTESTATION_REQUIRED = "attestation_required"


# Valid state transitions: source → set of allowed targets
_ALLOWED_TRANSITIONS: dict[PolicyState, frozenset[PolicyState]] = {
    PolicyState.DRAFT: frozenset({PolicyState.REVIEW, PolicyState.ARCHIVED}),
    PolicyState.REVIEW: frozenset({PolicyState.DRAFT, PolicyState.STAGED, PolicyState.ARCHIVED}),
    PolicyState.STAGED: frozenset({PolicyState.ACTIVE, PolicyState.REVIEW, PolicyState.ARCHIVED}),
    PolicyState.ACTIVE: frozenset({PolicyState.DEPRECATED}),
    PolicyState.DEPRECATED: frozenset({PolicyState.ARCHIVED}),
    PolicyState.ARCHIVED: frozenset(),
}


@dataclass
class LifecycleGate:
    """A single gate requirement that must pass before a transition is allowed."""

    gate_type: GateType
    target_state: PolicyState  # which transition this gate applies to
    threshold: float | int | None = None  # e.g. min approvals count, blast radius %
    required: bool = True  # if False, gate failure generates a warning, not a block

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_type": self.gate_type.value,
            "target_state": self.target_state.value,
            "threshold": self.threshold,
            "required": self.required,
        }


@dataclass
class GateEvaluation:
    """Result of evaluating a single gate."""

    gate: LifecycleGate
    passed: bool
    reason: str = ""


@dataclass
class RolloutStage:
    """One stage in a multi-step percentage rollout plan."""

    percentage: float  # 0.0–100.0 — fraction of traffic/agents to route to new policy
    duration_seconds: float  # how long to hold this stage before auto-advancing
    auto_advance: bool = True  # advance automatically when duration elapses


@dataclass
class RolloutPlan:
    """A staged rollout plan for promoting a policy from STAGED to ACTIVE."""

    stages: list[RolloutStage] = field(default_factory=list)
    current_stage_index: int = 0
    started_at: float | None = None

    @property
    def current_percentage(self) -> float:
        if not self.stages or self.current_stage_index >= len(self.stages):
            return 100.0
        return self.stages[self.current_stage_index].percentage

    @property
    def is_complete(self) -> bool:
        return self.current_stage_index >= len(self.stages)

    def advance(self) -> bool:
        """Move to the next rollout stage. Returns True if advanced, False if already complete."""
        if self.is_complete:
            return False
        self.current_stage_index += 1
        return True

    @classmethod
    def canary(cls, percentages: list[float], duration_seconds: float = 300.0) -> RolloutPlan:
        """Convenience constructor for a canary rollout with given percentage steps."""
        return cls(stages=[RolloutStage(p, duration_seconds) for p in percentages])


@dataclass
class TransitionRecord:
    """Immutable record of a state transition in the audit trail."""

    policy_id: str
    from_state: PolicyState | None
    to_state: PolicyState
    timestamp: float
    actor: str | None
    gate_evaluations: list[GateEvaluation] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "from_state": self.from_state.value if self.from_state else None,
            "to_state": self.to_state.value,
            "timestamp": self.timestamp,
            "actor": self.actor,
            "gates_checked": len(self.gate_evaluations),
            "gates_passed": sum(1 for g in self.gate_evaluations if g.passed),
            "notes": self.notes,
        }


@dataclass
class ManagedPolicy:
    """A governance policy tracked by the lifecycle orchestrator."""

    policy_id: str
    state: PolicyState = PolicyState.DRAFT
    approvals: list[str] = field(default_factory=list)  # approver IDs
    lint_clean: bool = False
    test_suite_passed: bool = False
    blast_radius_pct: float | None = None  # estimated impact percentage
    attestation_present: bool = False
    rollout_plan: RolloutPlan | None = None
    supersedes: list[str] = field(default_factory=list)  # policy IDs this replaces
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "state": self.state.value,
            "approvals": self.approvals,
            "lint_clean": self.lint_clean,
            "test_suite_passed": self.test_suite_passed,
            "blast_radius_pct": self.blast_radius_pct,
            "attestation_present": self.attestation_present,
            "rollout_stage": (self.rollout_plan.current_stage_index if self.rollout_plan else None),
            "rollout_pct": (self.rollout_plan.current_percentage if self.rollout_plan else None),
            "supersedes": self.supersedes,
            "metadata": self.metadata,
        }


@dataclass
class OrchestratorTransitionResult:
    """Full result returned by :meth:`PolicyLifecycleOrchestrator.transition`."""

    outcome: TransitionResult
    policy_id: str
    from_state: PolicyState | None
    to_state: PolicyState | None
    gate_evaluations: list[GateEvaluation] = field(default_factory=list)
    auto_deprecated: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.outcome == TransitionResult.SUCCESS


class PolicyLifecycleOrchestrator:
    """End-to-end lifecycle state machine for governance policies.

    Manages registered policies through the states:
    ``DRAFT → REVIEW → STAGED → ACTIVE → DEPRECATED → ARCHIVED``

    Each forward transition is guarded by configurable gate checks. The
    orchestrator maintains a complete audit trail of every transition.

    Example usage::

        orch = PolicyLifecycleOrchestrator()

        # Register a new policy
        policy = orch.register("pii-v2")
        orch.record_approval("pii-v2", "alice")
        orch.record_approval("pii-v2", "bob")
        orch.set_lint_clean("pii-v2", True)
        orch.set_test_suite_passed("pii-v2", True)

        # Submit for review
        result = orch.transition("pii-v2", PolicyState.REVIEW)

        # Stage with a canary rollout
        orch.set_rollout_plan("pii-v2", RolloutPlan.canary([10.0, 50.0, 100.0]))
        result = orch.transition("pii-v2", PolicyState.STAGED)

        # Activate (auto-deprecates superseded policies)
        result = orch.transition("pii-v2", PolicyState.ACTIVE, supersedes=["pii-v1"])
        print(result.auto_deprecated)  # ["pii-v1"]
    """

    def __init__(
        self,
        *,
        default_min_approvals: int = 2,
        default_blast_radius_limit: float = 30.0,
    ) -> None:
        self._policies: dict[str, ManagedPolicy] = {}
        self._gates: list[LifecycleGate] = self._default_gates(
            default_min_approvals, default_blast_radius_limit
        )
        self._audit_trail: list[TransitionRecord] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        policy_id: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ManagedPolicy:
        """Register a new policy in DRAFT state.

        Args:
            policy_id: Unique identifier for this policy.
            metadata: Optional arbitrary metadata dict.

        Returns:
            The newly created :class:`ManagedPolicy`.
        """
        policy = ManagedPolicy(
            policy_id=policy_id,
            metadata=metadata or {},
        )
        self._policies[policy_id] = policy
        self._record_transition(policy_id, None, PolicyState.DRAFT, actor=None)
        return policy

    def get(self, policy_id: str) -> ManagedPolicy | None:
        """Return the :class:`ManagedPolicy` for *policy_id*, or None."""
        return self._policies.get(policy_id)

    # ------------------------------------------------------------------
    # Gate data setters
    # ------------------------------------------------------------------

    def record_approval(self, policy_id: str, approver_id: str) -> bool:
        """Record an approval from *approver_id*. Deduplicates. Returns True if added."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        if approver_id not in policy.approvals:
            policy.approvals.append(approver_id)
            policy.updated_at = time.monotonic()
        return True

    def revoke_approval(self, policy_id: str, approver_id: str) -> bool:
        """Revoke an existing approval. Returns True if it was present."""
        policy = self._policies.get(policy_id)
        if policy is None or approver_id not in policy.approvals:
            return False
        policy.approvals.remove(approver_id)
        policy.updated_at = time.monotonic()
        return True

    def set_lint_clean(self, policy_id: str, clean: bool) -> bool:
        """Set the lint-clean status for a policy."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        policy.lint_clean = clean
        policy.updated_at = time.monotonic()
        return True

    def set_test_suite_passed(self, policy_id: str, passed: bool) -> bool:
        """Set the test-suite-pass status for a policy."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        policy.test_suite_passed = passed
        policy.updated_at = time.monotonic()
        return True

    def set_blast_radius(self, policy_id: str, pct: float) -> bool:
        """Set the estimated blast radius percentage (0-100)."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        policy.blast_radius_pct = max(0.0, min(100.0, pct))
        policy.updated_at = time.monotonic()
        return True

    def set_attestation(self, policy_id: str, present: bool) -> bool:
        """Mark whether a compliance attestation is present for this policy."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        policy.attestation_present = present
        policy.updated_at = time.monotonic()
        return True

    def set_rollout_plan(self, policy_id: str, plan: RolloutPlan) -> bool:
        """Attach a staged rollout plan to a policy."""
        policy = self._policies.get(policy_id)
        if policy is None:
            return False
        policy.rollout_plan = plan
        policy.updated_at = time.monotonic()
        return True

    # ------------------------------------------------------------------
    # Transition engine
    # ------------------------------------------------------------------

    def transition(
        self,
        policy_id: str,
        target_state: PolicyState,
        *,
        actor: str | None = None,
        notes: str = "",
        supersedes: list[str] | None = None,
        force: bool = False,
    ) -> OrchestratorTransitionResult:
        """Attempt to transition a policy to *target_state*.

        Args:
            policy_id: ID of the policy to transition.
            target_state: Desired new state.
            actor: Identifier of the agent/user requesting the transition.
            notes: Optional notes for the audit trail.
            supersedes: If transitioning to ACTIVE, these policy IDs will be
                auto-deprecated.
            force: If True, bypass required gate checks (use for emergencies only).

        Returns:
            :class:`OrchestratorTransitionResult` with outcome and gate details.
        """
        policy = self._policies.get(policy_id)
        if policy is None:
            return OrchestratorTransitionResult(
                outcome=TransitionResult.POLICY_NOT_FOUND,
                policy_id=policy_id,
                from_state=None,
                to_state=target_state,
                message=f"Policy '{policy_id}' not found.",
            )

        from_state = policy.state
        if target_state not in _ALLOWED_TRANSITIONS.get(from_state, frozenset()):
            return OrchestratorTransitionResult(
                outcome=TransitionResult.INVALID_TRANSITION,
                policy_id=policy_id,
                from_state=from_state,
                to_state=target_state,
                message=f"Transition {from_state.value} → {target_state.value} is not allowed.",
            )

        gate_evals = self._evaluate_gates(policy, target_state)
        blocking_failures = [g for g in gate_evals if not g.passed and g.gate.required]

        if blocking_failures and not force:
            reasons = "; ".join(g.reason for g in blocking_failures)
            return OrchestratorTransitionResult(
                outcome=TransitionResult.BLOCKED_BY_GATE,
                policy_id=policy_id,
                from_state=from_state,
                to_state=target_state,
                gate_evaluations=gate_evals,
                message=f"Gate(s) failed: {reasons}",
            )

        policy.state = target_state
        policy.updated_at = time.monotonic()

        if target_state == PolicyState.STAGED and policy.rollout_plan:
            policy.rollout_plan.started_at = time.monotonic()

        auto_deprecated: list[str] = []
        if target_state == PolicyState.ACTIVE and supersedes:
            for sid in supersedes:
                dep_result = self.transition(
                    sid, PolicyState.DEPRECATED, actor="orchestrator", notes="auto-superseded"
                )
                if dep_result.succeeded:
                    auto_deprecated.append(sid)
                    if sid not in policy.supersedes:
                        policy.supersedes.append(sid)

        self._record_transition(
            policy_id, from_state, target_state, actor=actor, gate_evals=gate_evals, notes=notes
        )

        return OrchestratorTransitionResult(
            outcome=TransitionResult.SUCCESS,
            policy_id=policy_id,
            from_state=from_state,
            to_state=target_state,
            gate_evaluations=gate_evals,
            auto_deprecated=auto_deprecated,
            message=f"Transitioned {from_state.value} → {target_state.value}.",
        )

    def advance_rollout(self, policy_id: str) -> bool:
        """Advance the rollout stage for a STAGED policy. Returns True if advanced."""
        policy = self._policies.get(policy_id)
        if policy is None or policy.state != PolicyState.STAGED or not policy.rollout_plan:
            return False
        return policy.rollout_plan.advance()

    # ------------------------------------------------------------------
    # Gate configuration
    # ------------------------------------------------------------------

    def add_gate(self, gate: LifecycleGate) -> None:
        """Add a custom gate to the orchestrator."""
        self._gates.append(gate)

    def remove_gates_for(self, target_state: PolicyState) -> int:
        """Remove all gates targeting *target_state*. Returns count removed."""
        before = len(self._gates)
        self._gates = [g for g in self._gates if g.target_state != target_state]
        return before - len(self._gates)

    # ------------------------------------------------------------------
    # Query / reporting
    # ------------------------------------------------------------------

    def policies_in_state(self, state: PolicyState) -> list[ManagedPolicy]:
        """Return all policies currently in *state*."""
        return [p for p in self._policies.values() if p.state == state]

    def audit_trail(
        self,
        *,
        policy_id: str | None = None,
        limit: int | None = None,
    ) -> list[TransitionRecord]:
        """Return the audit trail, optionally filtered by policy_id."""
        trail = self._audit_trail
        if policy_id is not None:
            trail = [r for r in trail if r.policy_id == policy_id]
        if limit is not None:
            trail = trail[-limit:]
        return trail

    def summary(self) -> dict[str, Any]:
        """Return aggregate statistics about all managed policies."""
        state_counts: dict[str, int] = {}
        for p in self._policies.values():
            state_counts[p.state.value] = state_counts.get(p.state.value, 0) + 1
        return {
            "total_policies": len(self._policies),
            "state_counts": state_counts,
            "audit_trail_length": len(self._audit_trail),
            "gates_configured": len(self._gates),
        }

    def export_policy(self, policy_id: str) -> dict[str, Any] | None:
        """Export a policy's full state as a plain dict."""
        policy = self._policies.get(policy_id)
        return policy.to_dict() if policy else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_gates(
        self, policy: ManagedPolicy, target_state: PolicyState
    ) -> list[GateEvaluation]:
        evals: list[GateEvaluation] = []
        for gate in self._gates:
            if gate.target_state != target_state:
                continue
            passed, reason = self._check_gate(gate, policy)
            evals.append(GateEvaluation(gate=gate, passed=passed, reason=reason))
        return evals

    @staticmethod
    def _check_gate(gate: LifecycleGate, policy: ManagedPolicy) -> tuple[bool, str]:
        if gate.gate_type == GateType.MIN_APPROVALS:
            threshold = int(gate.threshold or 1)
            count = len(policy.approvals)
            if count >= threshold:
                return True, ""
            return False, f"needs {threshold} approvals, has {count}"

        if gate.gate_type == GateType.LINT_CLEAN:
            if policy.lint_clean:
                return True, ""
            return False, "lint check has not passed"

        if gate.gate_type == GateType.TEST_SUITE_PASS:
            if policy.test_suite_passed:
                return True, ""
            return False, "test suite has not passed"

        if gate.gate_type == GateType.BLAST_RADIUS_BELOW:
            if policy.blast_radius_pct is None:
                return False, "blast radius not assessed"
            blast_radius_threshold = float(gate.threshold or 50.0)
            if policy.blast_radius_pct <= blast_radius_threshold:
                return True, ""
            return (
                False,
                f"blast radius {policy.blast_radius_pct:.1f}% > limit "
                f"{blast_radius_threshold:.1f}%",
            )

        if gate.gate_type == GateType.ATTESTATION_REQUIRED:
            if policy.attestation_present:
                return True, ""
            return False, "attestation not present"

        return True, ""

    def _record_transition(
        self,
        policy_id: str,
        from_state: PolicyState | None,
        to_state: PolicyState,
        *,
        actor: str | None = None,
        gate_evals: list[GateEvaluation] | None = None,
        notes: str = "",
    ) -> None:
        self._audit_trail.append(
            TransitionRecord(
                policy_id=policy_id,
                from_state=from_state,
                to_state=to_state,
                timestamp=time.monotonic(),
                actor=actor,
                gate_evaluations=gate_evals or [],
                notes=notes,
            )
        )

    @staticmethod
    def _default_gates(min_approvals: int, blast_radius_limit: float) -> list[LifecycleGate]:
        return [
            LifecycleGate(GateType.MIN_APPROVALS, PolicyState.REVIEW, threshold=min_approvals),
            LifecycleGate(GateType.LINT_CLEAN, PolicyState.STAGED),
            LifecycleGate(GateType.TEST_SUITE_PASS, PolicyState.STAGED),
            LifecycleGate(
                GateType.BLAST_RADIUS_BELOW, PolicyState.ACTIVE, threshold=blast_radius_limit
            ),
        ]
