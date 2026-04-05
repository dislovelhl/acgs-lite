"""
Tests for ACGS-2 Constitutional Refoundation System.
Constitutional Hash: 608508a9bd224290

Validates the RefoundationEngine lifecycle including:
- Human-only proposal creation
- Multi-role (LEGISLATIVE + EXECUTIVE + JUDICIAL) approval
- Sandbox execution gating
- Epoch creation and history preservation
"""

from __future__ import annotations

import pytest

from enhanced_agent_bus.constitutional.invariants import (
    InvariantDefinition,
    InvariantManifest,
    InvariantScope,
    get_default_manifest,
)
from enhanced_agent_bus.constitutional.refoundation import (
    ConstitutionalEpoch,
    RefoundationApproval,
    RefoundationEngine,
    RefoundationError,
    RefoundationProposal,
    RefoundationStatus,
    SandboxExecutionResult,
)

_CONSTITUTIONAL_HASH = "608508a9bd224290"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(extra_invariant_id: str = "INV-TEST") -> InvariantManifest:
    """Build a minimal InvariantManifest for testing."""
    return InvariantManifest(
        constitutional_hash=_CONSTITUTIONAL_HASH,
        invariants=[
            InvariantDefinition(
                invariant_id=extra_invariant_id,
                name="Test invariant",
                scope=InvariantScope.HARD,
            ),
        ],
    )


def _long_justification() -> str:
    return (
        "This refoundation is necessary because the existing MACI separation "
        "invariant must be updated to support multi-agent collaboration patterns."
    )


def _create_engine_with_proposal(
    *,
    proposer_id: str = "human-1",
) -> tuple[RefoundationEngine, RefoundationProposal]:
    """Create an engine and a drafted proposal."""
    engine = RefoundationEngine()
    manifest = _make_manifest()
    proposal = engine.create_proposal(
        proposer_id=proposer_id,
        proposer_role="human_operator",
        current_epoch_id="epoch-0",
        proposed_invariant_changes={"INV-001": "Updated separation rules"},
        proposed_manifest=manifest,
        justification=_long_justification(),
        risk_assessment="Low risk — additive change only",
        rollback_plan="Revert to previous epoch manifest",
    )
    return engine, proposal


def _passing_sandbox() -> SandboxExecutionResult:
    return SandboxExecutionResult(
        sandbox_id="sandbox-1",
        passed=True,
        governance_metrics_before={"accuracy": 0.95},
        governance_metrics_after={"accuracy": 0.96},
        degradation_detected=False,
        test_duration_seconds=12.5,
    )


def _failing_sandbox() -> SandboxExecutionResult:
    return SandboxExecutionResult(
        sandbox_id="sandbox-2",
        passed=False,
        degradation_detected=True,
        test_duration_seconds=3.1,
        error_details="Governance accuracy dropped below threshold",
    )


def _approve_all_roles(
    engine: RefoundationEngine,
    proposal_id: str,
) -> RefoundationProposal:
    """Add approvals from all three MACI roles."""
    engine.add_approval(proposal_id, "legislative", "approver-leg", True, "Justified change")
    engine.add_approval(proposal_id, "executive", "approver-exec", True, "Operationally sound")
    return engine.add_approval(
        proposal_id, "judicial", "approver-jud", True, "Constitutionally valid"
    )


def _fully_approve_proposal(
    engine: RefoundationEngine,
    proposal: RefoundationProposal,
) -> RefoundationProposal:
    """Submit, approve all roles, and record passing sandbox."""
    engine.submit_for_review(proposal.proposal_id)
    engine.add_approval(proposal.proposal_id, "legislative", "approver-leg", True, "OK")
    engine.add_approval(proposal.proposal_id, "executive", "approver-exec", True, "OK")
    engine.add_approval(proposal.proposal_id, "judicial", "approver-jud", True, "OK")
    return engine.record_sandbox_results(proposal.proposal_id, _passing_sandbox())


# ---------------------------------------------------------------------------
# 1-4: Proposal creation
# ---------------------------------------------------------------------------


class TestProposalCreation:
    """Tests for refoundation proposal creation."""

    def test_human_operator_can_create_proposal(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        assert proposal.status == RefoundationStatus.DRAFTED
        assert proposal.proposer_role == "human_operator"
        assert proposal.proposer_id == "human-1"
        assert proposal.proposal_id in engine._proposals

    def test_agent_role_cannot_create_proposal(self) -> None:
        engine = RefoundationEngine()
        with pytest.raises(RefoundationError, match="human operators"):
            engine.create_proposal(
                proposer_id="agent-1",
                proposer_role="legislative",
                current_epoch_id="epoch-0",
                proposed_invariant_changes={"INV-001": "change"},
                proposed_manifest=_make_manifest(),
                justification=_long_justification(),
                risk_assessment="risk",
                rollback_plan="plan",
            )

    def test_short_justification_rejected(self) -> None:
        engine = RefoundationEngine()
        with pytest.raises(RefoundationError, match="at least 50 characters"):
            engine.create_proposal(
                proposer_id="human-1",
                proposer_role="human_operator",
                current_epoch_id="epoch-0",
                proposed_invariant_changes={"INV-001": "change"},
                proposed_manifest=_make_manifest(),
                justification="Too short",
                risk_assessment="risk",
                rollback_plan="plan",
            )

    def test_proposal_starts_in_drafted_status(self) -> None:
        _, proposal = _create_engine_with_proposal()
        assert proposal.status == RefoundationStatus.DRAFTED


# ---------------------------------------------------------------------------
# 5-10: Approval flow
# ---------------------------------------------------------------------------


class TestApprovalFlow:
    """Tests for multi-role approval flow."""

    def test_legislative_approval_recorded(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(
            proposal.proposal_id, "legislative", "approver-leg", True, "OK"
        )
        assert updated.legislative_approval is not None
        assert updated.legislative_approval.approved is True
        assert updated.legislative_approval.role == "legislative"

    def test_executive_approval_recorded(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(
            proposal.proposal_id, "executive", "approver-exec", True, "OK"
        )
        assert updated.executive_approval is not None
        assert updated.executive_approval.approved is True

    def test_judicial_approval_recorded(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(proposal.proposal_id, "judicial", "approver-jud", True, "OK")
        assert updated.judicial_approval is not None
        assert updated.judicial_approval.approved is True

    def test_self_approval_rejected(self) -> None:
        engine, proposal = _create_engine_with_proposal(proposer_id="human-1")
        engine.submit_for_review(proposal.proposal_id)
        with pytest.raises(RefoundationError, match="proposer cannot approve"):
            engine.add_approval(proposal.proposal_id, "legislative", "human-1", True, "OK")

    def test_duplicate_role_approval_rejected(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        engine.add_approval(proposal.proposal_id, "legislative", "approver-leg", True, "OK")
        with pytest.raises(RefoundationError, match="already provided"):
            engine.add_approval(proposal.proposal_id, "legislative", "approver-other", True, "OK")

    def test_invalid_role_rejected(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        with pytest.raises(RefoundationError, match="Invalid role"):
            engine.add_approval(proposal.proposal_id, "admin", "approver-1", True, "OK")


# ---------------------------------------------------------------------------
# 11-12: Sandbox
# ---------------------------------------------------------------------------


class TestSandbox:
    """Tests for sandbox execution gating."""

    def test_sandbox_results_recorded(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        # Need at least one approval to move to UNDER_REVIEW
        engine.add_approval(proposal.proposal_id, "legislative", "approver-leg", True, "OK")
        results = _passing_sandbox()
        updated = engine.record_sandbox_results(proposal.proposal_id, results)
        assert updated.sandbox_results is not None
        assert updated.sandbox_results.passed is True

    def test_sandbox_failure_blocks_activation(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        _approve_all_roles(engine, proposal.proposal_id)
        engine.record_sandbox_results(proposal.proposal_id, _failing_sandbox())
        # Status should be REJECTED due to failed sandbox
        stored = engine.get_proposal(proposal.proposal_id)
        assert stored is not None
        assert stored.status == RefoundationStatus.REJECTED


# ---------------------------------------------------------------------------
# 13-18: Activation
# ---------------------------------------------------------------------------


class TestActivation:
    """Tests for refoundation activation and epoch creation."""

    def test_activation_with_full_approval_creates_epoch(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        _fully_approve_proposal(engine, proposal)
        epoch = engine.activate(proposal.proposal_id)
        assert isinstance(epoch, ConstitutionalEpoch)
        assert epoch.epoch_number == 1
        assert epoch.created_by == "human-1"

    def test_activation_without_all_approvals_raises(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        engine.add_approval(proposal.proposal_id, "legislative", "approver-leg", True, "OK")
        # Only one approval — status is UNDER_REVIEW, not APPROVED
        with pytest.raises(RefoundationError, match="APPROVED"):
            engine.activate(proposal.proposal_id)

    def test_activation_without_sandbox_raises(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        _approve_all_roles(engine, proposal.proposal_id)
        # All approved but no sandbox → status is SANDBOX_TESTING
        with pytest.raises(RefoundationError, match="APPROVED"):
            engine.activate(proposal.proposal_id)

    def test_activation_creates_correct_invariant_hash(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        _fully_approve_proposal(engine, proposal)
        epoch = engine.activate(proposal.proposal_id)
        assert epoch.invariant_manifest.invariant_hash != ""
        assert epoch.invariant_manifest.invariant_hash == (
            proposal.proposed_manifest.invariant_hash
        )

    def test_old_epoch_preserved_after_activation(self) -> None:
        engine, p1 = _create_engine_with_proposal()
        _fully_approve_proposal(engine, p1)
        epoch1 = engine.activate(p1.proposal_id)

        # Create second refoundation
        p2 = engine.create_proposal(
            proposer_id="human-2",
            proposer_role="human_operator",
            current_epoch_id=epoch1.epoch_id,
            proposed_invariant_changes={"INV-002": "New change"},
            proposed_manifest=_make_manifest("INV-TEST-2"),
            justification=_long_justification(),
            risk_assessment="Medium risk",
            rollback_plan="Revert to epoch 1",
        )
        _fully_approve_proposal(engine, p2)
        engine.activate(p2.proposal_id)

        history = engine.get_epoch_history()
        assert len(history) == 2
        assert history[0].epoch_id == epoch1.epoch_id

    def test_new_epoch_has_correct_predecessor(self) -> None:
        engine, p1 = _create_engine_with_proposal()
        _fully_approve_proposal(engine, p1)
        epoch1 = engine.activate(p1.proposal_id)

        p2 = engine.create_proposal(
            proposer_id="human-2",
            proposer_role="human_operator",
            current_epoch_id=epoch1.epoch_id,
            proposed_invariant_changes={"INV-002": "Change"},
            proposed_manifest=_make_manifest("INV-TEST-2"),
            justification=_long_justification(),
            risk_assessment="Risk assessment",
            rollback_plan="Rollback plan",
        )
        _fully_approve_proposal(engine, p2)
        epoch2 = engine.activate(p2.proposal_id)

        assert epoch2.predecessor_epoch_id == epoch1.epoch_id
        assert epoch2.epoch_number == 2


# ---------------------------------------------------------------------------
# 19-20: Status transitions
# ---------------------------------------------------------------------------


class TestStatusTransitions:
    """Tests for the full status transition lifecycle."""

    def test_full_lifecycle_drafted_to_activated(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        assert proposal.status == RefoundationStatus.DRAFTED

        submitted = engine.submit_for_review(proposal.proposal_id)
        assert submitted.status == RefoundationStatus.SUBMITTED

        after_first = engine.add_approval(
            proposal.proposal_id, "legislative", "approver-leg", True, "OK"
        )
        assert after_first.status == RefoundationStatus.UNDER_REVIEW

        engine.add_approval(proposal.proposal_id, "executive", "approver-exec", True, "OK")
        after_all = engine.add_approval(
            proposal.proposal_id, "judicial", "approver-jud", True, "OK"
        )
        assert after_all.status == RefoundationStatus.SANDBOX_TESTING

        after_sandbox = engine.record_sandbox_results(proposal.proposal_id, _passing_sandbox())
        assert after_sandbox.status == RefoundationStatus.APPROVED

        epoch = engine.activate(proposal.proposal_id)
        stored = engine.get_proposal(proposal.proposal_id)
        assert stored is not None
        assert stored.status == RefoundationStatus.ACTIVATED
        assert stored.new_epoch_id == epoch.epoch_id

    def test_rejection_at_review_stage(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(
            proposal.proposal_id, "judicial", "approver-jud", False, "Not justified"
        )
        assert updated.status == RefoundationStatus.REJECTED


# ---------------------------------------------------------------------------
# 21-22: Epoch history
# ---------------------------------------------------------------------------


class TestEpochHistory:
    """Tests for epoch history integrity."""

    def test_epoch_history_returns_copy(self) -> None:
        engine, proposal = _create_engine_with_proposal()
        _fully_approve_proposal(engine, proposal)
        engine.activate(proposal.proposal_id)

        history = engine.get_epoch_history()
        history.clear()  # mutate the returned list

        assert len(engine.get_epoch_history()) == 1  # original unchanged

    def test_multiple_refoundations_create_chain(self) -> None:
        engine, p1 = _create_engine_with_proposal()
        _fully_approve_proposal(engine, p1)
        e1 = engine.activate(p1.proposal_id)

        p2 = engine.create_proposal(
            proposer_id="human-2",
            proposer_role="human_operator",
            current_epoch_id=e1.epoch_id,
            proposed_invariant_changes={"INV-002": "Second change"},
            proposed_manifest=_make_manifest("INV-T2"),
            justification=_long_justification(),
            risk_assessment="Risk",
            rollback_plan="Rollback",
        )
        _fully_approve_proposal(engine, p2)
        e2 = engine.activate(p2.proposal_id)

        p3 = engine.create_proposal(
            proposer_id="human-3",
            proposer_role="human_operator",
            current_epoch_id=e2.epoch_id,
            proposed_invariant_changes={"INV-003": "Third change"},
            proposed_manifest=_make_manifest("INV-T3"),
            justification=_long_justification(),
            risk_assessment="Risk",
            rollback_plan="Rollback",
        )
        _fully_approve_proposal(engine, p3)
        e3 = engine.activate(p3.proposal_id)

        history = engine.get_epoch_history()
        assert len(history) == 3
        assert history[0].epoch_number == 1
        assert history[1].epoch_number == 2
        assert history[2].epoch_number == 3
        assert history[1].predecessor_epoch_id == history[0].epoch_id
        assert history[2].predecessor_epoch_id == history[1].epoch_id
        assert engine.get_current_epoch() == e3
