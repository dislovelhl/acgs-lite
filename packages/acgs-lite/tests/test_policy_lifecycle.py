"""Tests for constitution/policy_lifecycle.py.

Covers the PolicyLifecycleOrchestrator state machine, gate checks,
rollout plans, audit trail, supersession, and query/reporting helpers.
"""


from acgs_lite.constitution.policy_lifecycle import (
    _ALLOWED_TRANSITIONS,
    GateEvaluation,
    GateType,
    LifecycleGate,
    ManagedPolicy,
    OrchestratorTransitionResult,
    PolicyLifecycleOrchestrator,
    PolicyState,
    RolloutPlan,
    RolloutStage,
    TransitionRecord,
    TransitionResult,
)

# ---------------------------------------------------------------------------
# Enums / dataclasses
# ---------------------------------------------------------------------------


class TestPolicyState:
    def test_all_states_exist(self):
        states = {s.value for s in PolicyState}
        assert states == {"draft", "review", "staged", "active", "deprecated", "archived"}


class TestTransitionResult:
    def test_values(self):
        assert TransitionResult.SUCCESS.value == "success"
        assert TransitionResult.BLOCKED_BY_GATE.value == "blocked_by_gate"


class TestGateType:
    def test_values(self):
        assert GateType.MIN_APPROVALS.value == "min_approvals"
        assert GateType.ATTESTATION_REQUIRED.value == "attestation_required"


class TestAllowedTransitions:
    def test_draft_can_go_to_review(self):
        assert PolicyState.REVIEW in _ALLOWED_TRANSITIONS[PolicyState.DRAFT]

    def test_archived_is_terminal(self):
        assert len(_ALLOWED_TRANSITIONS[PolicyState.ARCHIVED]) == 0

    def test_active_can_only_deprecate(self):
        assert _ALLOWED_TRANSITIONS[PolicyState.ACTIVE] == frozenset({PolicyState.DEPRECATED})


# ---------------------------------------------------------------------------
# RolloutPlan
# ---------------------------------------------------------------------------


class TestRolloutPlan:
    def test_empty_plan(self):
        plan = RolloutPlan()
        assert plan.current_percentage == 100.0
        assert plan.is_complete is True
        assert plan.advance() is False

    def test_canary_factory(self):
        plan = RolloutPlan.canary([10.0, 50.0, 100.0], duration_seconds=120.0)
        assert len(plan.stages) == 3
        assert plan.current_percentage == 10.0
        assert plan.is_complete is False

    def test_advance_through_stages(self):
        plan = RolloutPlan.canary([10.0, 50.0, 100.0])
        assert plan.current_stage_index == 0
        assert plan.advance() is True
        assert plan.current_stage_index == 1
        assert plan.advance() is True
        assert plan.current_stage_index == 2
        assert plan.advance() is True
        assert plan.is_complete is True
        assert plan.advance() is False

    def test_current_percentage_after_complete(self):
        plan = RolloutPlan.canary([25.0])
        plan.advance()
        assert plan.current_percentage == 100.0


class TestRolloutStage:
    def test_defaults(self):
        stage = RolloutStage(percentage=50.0, duration_seconds=300.0)
        assert stage.auto_advance is True


# ---------------------------------------------------------------------------
# LifecycleGate / GateEvaluation
# ---------------------------------------------------------------------------


class TestLifecycleGate:
    def test_to_dict(self):
        gate = LifecycleGate(
            gate_type=GateType.MIN_APPROVALS,
            target_state=PolicyState.REVIEW,
            threshold=2,
        )
        d = gate.to_dict()
        assert d["gate_type"] == "min_approvals"
        assert d["target_state"] == "review"
        assert d["threshold"] == 2
        assert d["required"] is True


class TestGateEvaluation:
    def test_fields(self):
        gate = LifecycleGate(GateType.LINT_CLEAN, PolicyState.STAGED)
        ev = GateEvaluation(gate=gate, passed=True, reason="")
        assert ev.passed is True


# ---------------------------------------------------------------------------
# TransitionRecord
# ---------------------------------------------------------------------------


class TestTransitionRecord:
    def test_to_dict(self):
        rec = TransitionRecord(
            policy_id="p1",
            from_state=PolicyState.DRAFT,
            to_state=PolicyState.REVIEW,
            timestamp=12345.0,
            actor="alice",
            notes="initial",
        )
        d = rec.to_dict()
        assert d["policy_id"] == "p1"
        assert d["from_state"] == "draft"
        assert d["to_state"] == "review"
        assert d["actor"] == "alice"

    def test_to_dict_none_from_state(self):
        rec = TransitionRecord(
            policy_id="p1",
            from_state=None,
            to_state=PolicyState.DRAFT,
            timestamp=1.0,
            actor=None,
        )
        d = rec.to_dict()
        assert d["from_state"] is None


# ---------------------------------------------------------------------------
# ManagedPolicy
# ---------------------------------------------------------------------------


class TestManagedPolicy:
    def test_default_state_is_draft(self):
        p = ManagedPolicy(policy_id="pol-1")
        assert p.state == PolicyState.DRAFT

    def test_to_dict(self):
        p = ManagedPolicy(policy_id="pol-2", metadata={"version": 1})
        d = p.to_dict()
        assert d["policy_id"] == "pol-2"
        assert d["state"] == "draft"
        assert d["metadata"] == {"version": 1}
        assert d["rollout_stage"] is None
        assert d["rollout_pct"] is None

    def test_to_dict_with_rollout(self):
        p = ManagedPolicy(policy_id="pol-3")
        p.rollout_plan = RolloutPlan.canary([10.0, 100.0])
        d = p.to_dict()
        assert d["rollout_stage"] == 0
        assert d["rollout_pct"] == 10.0


# ---------------------------------------------------------------------------
# OrchestratorTransitionResult
# ---------------------------------------------------------------------------


class TestOrchestratorTransitionResult:
    def test_succeeded_property(self):
        r = OrchestratorTransitionResult(
            outcome=TransitionResult.SUCCESS,
            policy_id="p",
            from_state=PolicyState.DRAFT,
            to_state=PolicyState.REVIEW,
        )
        assert r.succeeded is True

    def test_failed_property(self):
        r = OrchestratorTransitionResult(
            outcome=TransitionResult.BLOCKED_BY_GATE,
            policy_id="p",
            from_state=PolicyState.DRAFT,
            to_state=PolicyState.REVIEW,
        )
        assert r.succeeded is False


# ---------------------------------------------------------------------------
# PolicyLifecycleOrchestrator
# ---------------------------------------------------------------------------


class TestOrchestrator:
    def _make_ready_for_review(self, orch, pid, approvers=2):
        """Helper: register and add enough approvals to pass the REVIEW gate."""
        orch.register(pid)
        for i in range(approvers):
            orch.record_approval(pid, f"approver-{i}")

    def _make_ready_for_staged(self, orch, pid):
        """Helper: get a policy all the way to REVIEW, set lint+tests for STAGED."""
        self._make_ready_for_review(orch, pid)
        result = orch.transition(pid, PolicyState.REVIEW, actor="test")
        assert result.succeeded
        orch.set_lint_clean(pid, True)
        orch.set_test_suite_passed(pid, True)

    def test_register(self):
        orch = PolicyLifecycleOrchestrator()
        p = orch.register("p1", metadata={"v": 1})
        assert p.state == PolicyState.DRAFT
        assert p.metadata == {"v": 1}

    def test_get(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.get("p1") is not None
        assert orch.get("missing") is None

    def test_transition_not_found(self):
        orch = PolicyLifecycleOrchestrator()
        r = orch.transition("ghost", PolicyState.REVIEW)
        assert r.outcome == TransitionResult.POLICY_NOT_FOUND

    def test_invalid_transition(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        r = orch.transition("p1", PolicyState.ACTIVE)
        assert r.outcome == TransitionResult.INVALID_TRANSITION

    def test_transition_draft_to_review_blocked_by_approvals(self):
        orch = PolicyLifecycleOrchestrator(default_min_approvals=2)
        orch.register("p1")
        # Only 1 approval, need 2
        orch.record_approval("p1", "alice")
        r = orch.transition("p1", PolicyState.REVIEW)
        assert r.outcome == TransitionResult.BLOCKED_BY_GATE
        assert "approvals" in r.message

    def test_transition_draft_to_review_success(self):
        orch = PolicyLifecycleOrchestrator(default_min_approvals=2)
        self._make_ready_for_review(orch, "p1")
        r = orch.transition("p1", PolicyState.REVIEW, actor="admin")
        assert r.succeeded
        assert orch.get("p1").state == PolicyState.REVIEW

    def test_transition_review_to_staged_blocked_by_lint(self):
        orch = PolicyLifecycleOrchestrator(default_min_approvals=1)
        orch.register("p1")
        orch.record_approval("p1", "a")
        orch.transition("p1", PolicyState.REVIEW)
        # lint not clean, tests not passed
        r = orch.transition("p1", PolicyState.STAGED)
        assert r.outcome == TransitionResult.BLOCKED_BY_GATE

    def test_transition_review_to_staged_success(self):
        orch = PolicyLifecycleOrchestrator()
        self._make_ready_for_staged(orch, "p1")
        r = orch.transition("p1", PolicyState.STAGED)
        assert r.succeeded

    def test_transition_staged_to_active_blocked_by_blast_radius(self):
        orch = PolicyLifecycleOrchestrator(default_blast_radius_limit=30.0)
        self._make_ready_for_staged(orch, "p1")
        orch.transition("p1", PolicyState.STAGED)
        # blast radius not set
        r = orch.transition("p1", PolicyState.ACTIVE)
        assert r.outcome == TransitionResult.BLOCKED_BY_GATE

    def test_transition_staged_to_active_success(self):
        orch = PolicyLifecycleOrchestrator(default_blast_radius_limit=30.0)
        self._make_ready_for_staged(orch, "p1")
        orch.transition("p1", PolicyState.STAGED)
        orch.set_blast_radius("p1", 10.0)
        r = orch.transition("p1", PolicyState.ACTIVE)
        assert r.succeeded

    def test_force_bypasses_gates(self):
        orch = PolicyLifecycleOrchestrator(default_min_approvals=5)
        orch.register("p1")
        r = orch.transition("p1", PolicyState.REVIEW, force=True)
        assert r.succeeded

    def test_supersession(self):
        orch = PolicyLifecycleOrchestrator(default_blast_radius_limit=50.0)
        # Create old policy and advance to ACTIVE
        self._make_ready_for_staged(orch, "old")
        orch.transition("old", PolicyState.STAGED)
        orch.set_blast_radius("old", 5.0)
        orch.transition("old", PolicyState.ACTIVE)

        # Create new policy and activate with supersedes
        self._make_ready_for_staged(orch, "new")
        orch.transition("new", PolicyState.STAGED)
        orch.set_blast_radius("new", 5.0)
        r = orch.transition("new", PolicyState.ACTIVE, supersedes=["old"])
        assert r.succeeded
        assert "old" in r.auto_deprecated
        assert orch.get("old").state == PolicyState.DEPRECATED

    def test_rollout_plan_started_on_staged(self):
        orch = PolicyLifecycleOrchestrator()
        self._make_ready_for_staged(orch, "p1")
        plan = RolloutPlan.canary([10.0, 100.0])
        orch.set_rollout_plan("p1", plan)
        orch.transition("p1", PolicyState.STAGED)
        assert orch.get("p1").rollout_plan.started_at is not None


class TestOrchestratorApprovals:
    def test_record_approval(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.record_approval("p1", "alice") is True
        assert "alice" in orch.get("p1").approvals

    def test_record_approval_deduplicates(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        orch.record_approval("p1", "alice")
        orch.record_approval("p1", "alice")
        assert orch.get("p1").approvals.count("alice") == 1

    def test_record_approval_missing_policy(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.record_approval("nope", "alice") is False

    def test_revoke_approval(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        orch.record_approval("p1", "alice")
        assert orch.revoke_approval("p1", "alice") is True
        assert "alice" not in orch.get("p1").approvals

    def test_revoke_missing(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.revoke_approval("p1", "nobody") is False

    def test_revoke_missing_policy(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.revoke_approval("nope", "a") is False


class TestOrchestratorSetters:
    def test_set_lint_clean(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.set_lint_clean("p1", True) is True
        assert orch.get("p1").lint_clean is True

    def test_set_lint_clean_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.set_lint_clean("nope", True) is False

    def test_set_test_suite_passed(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.set_test_suite_passed("p1", True) is True
        assert orch.get("p1").test_suite_passed is True

    def test_set_test_suite_passed_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.set_test_suite_passed("nope", True) is False

    def test_set_blast_radius(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.set_blast_radius("p1", 25.0) is True
        assert orch.get("p1").blast_radius_pct == 25.0

    def test_set_blast_radius_clamps(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        orch.set_blast_radius("p1", 150.0)
        assert orch.get("p1").blast_radius_pct == 100.0
        orch.set_blast_radius("p1", -10.0)
        assert orch.get("p1").blast_radius_pct == 0.0

    def test_set_blast_radius_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.set_blast_radius("nope", 5.0) is False

    def test_set_attestation(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.set_attestation("p1", True) is True
        assert orch.get("p1").attestation_present is True

    def test_set_attestation_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.set_attestation("nope", True) is False

    def test_set_rollout_plan(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        plan = RolloutPlan.canary([10.0])
        assert orch.set_rollout_plan("p1", plan) is True
        assert orch.get("p1").rollout_plan is plan

    def test_set_rollout_plan_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.set_rollout_plan("nope", RolloutPlan()) is False


class TestOrchestratorAdvanceRollout:
    def test_advance_rollout(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        plan = RolloutPlan.canary([10.0, 50.0, 100.0])
        orch.set_rollout_plan("p1", plan)
        # Must be in STAGED state
        orch.record_approval("p1", "a")
        orch.record_approval("p1", "b")
        orch.transition("p1", PolicyState.REVIEW, force=True)
        orch.set_lint_clean("p1", True)
        orch.set_test_suite_passed("p1", True)
        orch.transition("p1", PolicyState.STAGED)
        assert orch.advance_rollout("p1") is True
        assert plan.current_stage_index == 1

    def test_advance_rollout_not_staged(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        assert orch.advance_rollout("p1") is False

    def test_advance_rollout_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.advance_rollout("nope") is False


class TestOrchestratorGateConfig:
    def test_add_gate(self):
        orch = PolicyLifecycleOrchestrator()
        initial = len(orch._gates)
        orch.add_gate(LifecycleGate(GateType.ATTESTATION_REQUIRED, PolicyState.ACTIVE))
        assert len(orch._gates) == initial + 1

    def test_remove_gates_for(self):
        orch = PolicyLifecycleOrchestrator()
        removed = orch.remove_gates_for(PolicyState.REVIEW)
        assert removed >= 1


class TestOrchestratorReporting:
    def test_policies_in_state(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        orch.register("p2")
        assert len(orch.policies_in_state(PolicyState.DRAFT)) == 2

    def test_audit_trail(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        trail = orch.audit_trail()
        assert len(trail) >= 1
        assert trail[0].policy_id == "p1"

    def test_audit_trail_filter(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        orch.register("p2")
        trail = orch.audit_trail(policy_id="p1")
        assert all(r.policy_id == "p1" for r in trail)

    def test_audit_trail_limit(self):
        orch = PolicyLifecycleOrchestrator()
        for i in range(5):
            orch.register(f"p{i}")
        trail = orch.audit_trail(limit=2)
        assert len(trail) == 2

    def test_summary(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        s = orch.summary()
        assert s["total_policies"] == 1
        assert s["state_counts"]["draft"] == 1
        assert s["audit_trail_length"] >= 1
        assert s["gates_configured"] >= 1

    def test_export_policy(self):
        orch = PolicyLifecycleOrchestrator()
        orch.register("p1")
        exported = orch.export_policy("p1")
        assert exported is not None
        assert exported["policy_id"] == "p1"

    def test_export_missing(self):
        orch = PolicyLifecycleOrchestrator()
        assert orch.export_policy("nope") is None


class TestGateChecks:
    """Test individual gate check logic via the static _check_gate method."""

    def test_min_approvals_pass(self):
        gate = LifecycleGate(GateType.MIN_APPROVALS, PolicyState.REVIEW, threshold=2)
        policy = ManagedPolicy(policy_id="p", approvals=["a", "b"])
        passed, reason = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is True

    def test_min_approvals_fail(self):
        gate = LifecycleGate(GateType.MIN_APPROVALS, PolicyState.REVIEW, threshold=3)
        policy = ManagedPolicy(policy_id="p", approvals=["a"])
        passed, reason = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False
        assert "approvals" in reason

    def test_lint_clean_pass(self):
        gate = LifecycleGate(GateType.LINT_CLEAN, PolicyState.STAGED)
        policy = ManagedPolicy(policy_id="p", lint_clean=True)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is True

    def test_lint_clean_fail(self):
        gate = LifecycleGate(GateType.LINT_CLEAN, PolicyState.STAGED)
        policy = ManagedPolicy(policy_id="p", lint_clean=False)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False

    def test_test_suite_pass(self):
        gate = LifecycleGate(GateType.TEST_SUITE_PASS, PolicyState.STAGED)
        policy = ManagedPolicy(policy_id="p", test_suite_passed=True)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is True

    def test_test_suite_fail(self):
        gate = LifecycleGate(GateType.TEST_SUITE_PASS, PolicyState.STAGED)
        policy = ManagedPolicy(policy_id="p", test_suite_passed=False)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False

    def test_blast_radius_pass(self):
        gate = LifecycleGate(GateType.BLAST_RADIUS_BELOW, PolicyState.ACTIVE, threshold=30.0)
        policy = ManagedPolicy(policy_id="p", blast_radius_pct=10.0)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is True

    def test_blast_radius_fail(self):
        gate = LifecycleGate(GateType.BLAST_RADIUS_BELOW, PolicyState.ACTIVE, threshold=30.0)
        policy = ManagedPolicy(policy_id="p", blast_radius_pct=50.0)
        passed, reason = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False
        assert "50.0%" in reason

    def test_blast_radius_not_assessed(self):
        gate = LifecycleGate(GateType.BLAST_RADIUS_BELOW, PolicyState.ACTIVE, threshold=30.0)
        policy = ManagedPolicy(policy_id="p", blast_radius_pct=None)
        passed, reason = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False
        assert "not assessed" in reason

    def test_attestation_pass(self):
        gate = LifecycleGate(GateType.ATTESTATION_REQUIRED, PolicyState.ACTIVE)
        policy = ManagedPolicy(policy_id="p", attestation_present=True)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is True

    def test_attestation_fail(self):
        gate = LifecycleGate(GateType.ATTESTATION_REQUIRED, PolicyState.ACTIVE)
        policy = ManagedPolicy(policy_id="p", attestation_present=False)
        passed, _ = PolicyLifecycleOrchestrator._check_gate(gate, policy)
        assert passed is False
