"""Tests for constitutional/refoundation.py — Refoundation Engine."""

from __future__ import annotations

import pytest

from enhanced_agent_bus.constitutional.invariants import InvariantManifest
from enhanced_agent_bus.constitutional.refoundation import (
    ConstitutionalEpoch,
    RefoundationApproval,
    RefoundationEngine,
    RefoundationError,
    RefoundationProposal,
    RefoundationStatus,
    SandboxExecutionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LONG_JUSTIFICATION = "A" * 60  # > _MIN_JUSTIFICATION_LENGTH (50)
_SHORT_JUSTIFICATION = "short"


def _make_manifest() -> InvariantManifest:
    return InvariantManifest(constitutional_hash="608508a9bd224290")


def _create_engine_and_proposal(
    proposer_id: str = "human-1",
) -> tuple[RefoundationEngine, RefoundationProposal]:
    engine = RefoundationEngine()
    proposal = engine.create_proposal(
        proposer_id=proposer_id,
        proposer_role="human_operator",
        current_epoch_id="epoch-0",
        proposed_invariant_changes={"inv-1": "new value"},
        proposed_manifest=_make_manifest(),
        justification=_LONG_JUSTIFICATION,
        risk_assessment="low risk",
        rollback_plan="revert to previous epoch",
    )
    return engine, proposal


def _approve_all(engine: RefoundationEngine, proposal_id: str) -> RefoundationProposal:
    """Submit and approve from all three MACI roles."""
    engine.submit_for_review(proposal_id)
    engine.add_approval(proposal_id, "legislative", "approver-leg", True, "ok")
    engine.add_approval(proposal_id, "executive", "approver-exe", True, "ok")
    return engine.add_approval(proposal_id, "judicial", "approver-jud", True, "ok")


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestRefoundationDataModels:
    def test_refoundation_status_values(self) -> None:
        assert RefoundationStatus.DRAFTED == "drafted"
        assert RefoundationStatus.ACTIVATED == "activated"

    def test_refoundation_approval_defaults(self) -> None:
        approval = RefoundationApproval(
            role="legislative", approver_id="a1", approved=True, reasoning="ok"
        )
        assert approval.approved_at is not None

    def test_sandbox_execution_result_defaults(self) -> None:
        result = SandboxExecutionResult(sandbox_id="sb-1", passed=True)
        assert result.degradation_detected is False
        assert result.error_details is None

    def test_constitutional_epoch_auto_id(self) -> None:
        epoch = ConstitutionalEpoch(
            epoch_number=1,
            invariant_manifest=_make_manifest(),
            created_by="human-1",
            reason="test",
        )
        assert epoch.epoch_id  # UUID generated
        assert epoch.predecessor_epoch_id is None

    def test_refoundation_proposal_defaults(self) -> None:
        p = RefoundationProposal(
            current_epoch_id="e0",
            proposed_manifest=_make_manifest(),
            justification=_LONG_JUSTIFICATION,
            risk_assessment="low",
            rollback_plan="revert",
            proposer_id="h1",
        )
        assert p.status == RefoundationStatus.DRAFTED
        assert p.legislative_approval is None


# ---------------------------------------------------------------------------
# RefoundationEngine — create_proposal
# ---------------------------------------------------------------------------


class TestCreateProposal:
    def test_success(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        assert proposal.status == RefoundationStatus.DRAFTED
        assert proposal.proposer_role == "human_operator"

    def test_rejects_non_human_proposer(self) -> None:
        engine = RefoundationEngine()
        with pytest.raises(RefoundationError, match="human operators"):
            engine.create_proposal(
                proposer_id="bot-1",
                proposer_role="ai_agent",
                current_epoch_id="e0",
                proposed_invariant_changes={},
                proposed_manifest=_make_manifest(),
                justification=_LONG_JUSTIFICATION,
                risk_assessment="low",
                rollback_plan="revert",
            )

    def test_rejects_short_justification(self) -> None:
        engine = RefoundationEngine()
        with pytest.raises(RefoundationError, match="at least"):
            engine.create_proposal(
                proposer_id="human-1",
                proposer_role="human_operator",
                current_epoch_id="e0",
                proposed_invariant_changes={},
                proposed_manifest=_make_manifest(),
                justification=_SHORT_JUSTIFICATION,
                risk_assessment="low",
                rollback_plan="revert",
            )


# ---------------------------------------------------------------------------
# submit_for_review
# ---------------------------------------------------------------------------


class TestSubmitForReview:
    def test_success(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        updated = engine.submit_for_review(proposal.proposal_id)
        assert updated.status == RefoundationStatus.SUBMITTED
        assert updated.submitted_at is not None

    def test_rejects_non_drafted(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        engine.submit_for_review(proposal.proposal_id)
        with pytest.raises(RefoundationError, match="DRAFTED"):
            engine.submit_for_review(proposal.proposal_id)


# ---------------------------------------------------------------------------
# add_approval
# ---------------------------------------------------------------------------


class TestAddApproval:
    def test_single_approval_moves_to_under_review(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(proposal.proposal_id, "legislative", "approver-1", True, "ok")
        assert updated.status == RefoundationStatus.UNDER_REVIEW

    def test_invalid_role(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        engine.submit_for_review(proposal.proposal_id)
        with pytest.raises(RefoundationError, match="Invalid role"):
            engine.add_approval(proposal.proposal_id, "invalid_role", "a1", True, "ok")

    def test_self_approval_blocked(self) -> None:
        engine, proposal = _create_engine_and_proposal(proposer_id="human-1")
        engine.submit_for_review(proposal.proposal_id)
        with pytest.raises(RefoundationError, match="MACI separation"):
            engine.add_approval(proposal.proposal_id, "legislative", "human-1", True, "ok")

    def test_duplicate_role_blocked(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        engine.submit_for_review(proposal.proposal_id)
        engine.add_approval(proposal.proposal_id, "legislative", "a1", True, "ok")
        with pytest.raises(RefoundationError, match="already provided"):
            engine.add_approval(proposal.proposal_id, "legislative", "a2", True, "ok2")

    def test_rejection_sets_rejected(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        engine.submit_for_review(proposal.proposal_id)
        updated = engine.add_approval(proposal.proposal_id, "legislative", "a1", False, "disagree")
        assert updated.status == RefoundationStatus.REJECTED

    def test_all_three_approvals_moves_to_sandbox_testing(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        updated = _approve_all(engine, proposal.proposal_id)
        # No sandbox results yet -> SANDBOX_TESTING
        assert updated.status == RefoundationStatus.SANDBOX_TESTING

    def test_wrong_status_blocked(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        # Still DRAFTED, not SUBMITTED
        with pytest.raises(RefoundationError, match="SUBMITTED"):
            engine.add_approval(proposal.proposal_id, "legislative", "a1", True, "ok")


# ---------------------------------------------------------------------------
# record_sandbox_results
# ---------------------------------------------------------------------------


class TestRecordSandboxResults:
    def test_passed_sandbox_with_all_approvals(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        _approve_all(engine, proposal.proposal_id)
        results = SandboxExecutionResult(sandbox_id="sb-1", passed=True)
        updated = engine.record_sandbox_results(proposal.proposal_id, results)
        assert updated.status == RefoundationStatus.APPROVED

    def test_failed_sandbox_rejects(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        _approve_all(engine, proposal.proposal_id)
        results = SandboxExecutionResult(sandbox_id="sb-1", passed=False)
        updated = engine.record_sandbox_results(proposal.proposal_id, results)
        assert updated.status == RefoundationStatus.REJECTED

    def test_degradation_rejects(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        _approve_all(engine, proposal.proposal_id)
        results = SandboxExecutionResult(sandbox_id="sb-1", passed=True, degradation_detected=True)
        updated = engine.record_sandbox_results(proposal.proposal_id, results)
        assert updated.status == RefoundationStatus.REJECTED

    def test_wrong_status(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        results = SandboxExecutionResult(sandbox_id="sb-1", passed=True)
        with pytest.raises(RefoundationError, match="UNDER_REVIEW or SANDBOX_TESTING"):
            engine.record_sandbox_results(proposal.proposal_id, results)


# ---------------------------------------------------------------------------
# activate
# ---------------------------------------------------------------------------


class TestActivate:
    def _prepare_approved(self) -> tuple[RefoundationEngine, str]:
        engine, proposal = _create_engine_and_proposal()
        _approve_all(engine, proposal.proposal_id)
        results = SandboxExecutionResult(sandbox_id="sb-1", passed=True)
        engine.record_sandbox_results(proposal.proposal_id, results)
        return engine, proposal.proposal_id

    def test_activation_creates_epoch(self) -> None:
        engine, pid = self._prepare_approved()
        epoch = engine.activate(pid)
        assert isinstance(epoch, ConstitutionalEpoch)
        assert epoch.epoch_number == 1
        assert epoch.predecessor_epoch_id is None

    def test_epoch_history_appended(self) -> None:
        engine, pid = self._prepare_approved()
        engine.activate(pid)
        assert len(engine.get_epoch_history()) == 1
        assert engine.get_current_epoch() is not None

    def test_second_activation_increments_epoch(self) -> None:
        engine, pid1 = self._prepare_approved()
        epoch1 = engine.activate(pid1)

        # Create a second proposal
        p2 = engine.create_proposal(
            proposer_id="human-2",
            proposer_role="human_operator",
            current_epoch_id=epoch1.epoch_id,
            proposed_invariant_changes={"inv-2": "new"},
            proposed_manifest=_make_manifest(),
            justification=_LONG_JUSTIFICATION,
            risk_assessment="low",
            rollback_plan="revert",
        )
        engine.submit_for_review(p2.proposal_id)
        engine.add_approval(p2.proposal_id, "legislative", "a-leg", True, "ok")
        engine.add_approval(p2.proposal_id, "executive", "a-exe", True, "ok")
        engine.add_approval(p2.proposal_id, "judicial", "a-jud", True, "ok")
        engine.record_sandbox_results(
            p2.proposal_id, SandboxExecutionResult(sandbox_id="sb-2", passed=True)
        )

        epoch2 = engine.activate(p2.proposal_id)
        assert epoch2.epoch_number == 2
        assert epoch2.predecessor_epoch_id == epoch1.epoch_id
        assert len(engine.get_epoch_history()) == 2

    def test_non_approved_blocked(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        with pytest.raises(RefoundationError, match="APPROVED"):
            engine.activate(proposal.proposal_id)

    def test_proposal_not_found(self) -> None:
        engine = RefoundationEngine()
        with pytest.raises(RefoundationError, match="not found"):
            engine.activate("nonexistent-id")


# ---------------------------------------------------------------------------
# get_proposal / get_current_epoch / get_epoch_history
# ---------------------------------------------------------------------------


class TestAccessors:
    def test_get_proposal_returns_none_for_missing(self) -> None:
        engine = RefoundationEngine()
        assert engine.get_proposal("nope") is None

    def test_get_proposal_returns_proposal(self) -> None:
        engine, proposal = _create_engine_and_proposal()
        assert engine.get_proposal(proposal.proposal_id) is not None

    def test_get_current_epoch_initially_none(self) -> None:
        engine = RefoundationEngine()
        assert engine.get_current_epoch() is None

    def test_get_epoch_history_initially_empty(self) -> None:
        engine = RefoundationEngine()
        assert engine.get_epoch_history() == []

    def test_epoch_history_returns_copy(self) -> None:
        engine = RefoundationEngine()
        h1 = engine.get_epoch_history()
        h2 = engine.get_epoch_history()
        assert h1 is not h2
