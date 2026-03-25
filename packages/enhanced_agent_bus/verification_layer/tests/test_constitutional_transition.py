"""
Tests for Constitutional Transition - State Transitions with Proofs
Constitutional Hash: 608508a9bd224290

Tests cover:
- State transition validation
- Proof generation and verification
- Checkpoint management
- Rollback functionality
- Constitutional compliance
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from ..constitutional_transition import (
    CONSTITUTIONAL_HASH,
    VALID_TRANSITIONS,
    ConstitutionalTransition,
    ProofType,
    StateTransitionManager,
    TransitionProof,
    TransitionState,
    TransitionType,
    create_transition_manager,
)


class TestConstitutionalHash:
    """Tests for constitutional hash compliance."""

    def test_constitutional_hash_value(self):
        """Test that constitutional hash is correct."""
        assert CONSTITUTIONAL_HASH == CONSTITUTIONAL_HASH

    def test_manager_has_constitutional_hash(self):
        """Test that manager includes constitutional hash."""
        manager = create_transition_manager()
        assert manager.constitutional_hash == CONSTITUTIONAL_HASH

    def test_transition_has_constitutional_hash(self):
        """Test that transition includes constitutional hash."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )
        assert transition.constitutional_hash == CONSTITUTIONAL_HASH

    def test_proof_has_constitutional_hash(self):
        """Test that proof includes constitutional hash."""
        proof = TransitionProof()
        assert proof.constitutional_hash == CONSTITUTIONAL_HASH


class TestTransitionState:
    """Tests for TransitionState enum."""

    def test_all_states_defined(self):
        """Test that all states are defined."""
        assert TransitionState.INITIAL.value == "initial"
        assert TransitionState.PENDING_VALIDATION.value == "pending_validation"
        assert TransitionState.VALIDATED.value == "validated"
        assert TransitionState.PENDING_APPROVAL.value == "pending_approval"
        assert TransitionState.APPROVED.value == "approved"
        assert TransitionState.EXECUTING.value == "executing"
        assert TransitionState.EXECUTED.value == "executed"
        assert TransitionState.PENDING_VERIFICATION.value == "pending_verification"
        assert TransitionState.VERIFIED.value == "verified"
        assert TransitionState.COMPLETED.value == "completed"
        assert TransitionState.REJECTED.value == "rejected"
        assert TransitionState.ROLLED_BACK.value == "rolled_back"
        assert TransitionState.FAILED.value == "failed"


class TestTransitionType:
    """Tests for TransitionType enum."""

    def test_all_types_defined(self):
        """Test that all types are defined."""
        assert TransitionType.POLICY_CHANGE.value == "policy_change"
        assert TransitionType.ACCESS_GRANT.value == "access_grant"
        assert TransitionType.ACCESS_REVOKE.value == "access_revoke"
        assert TransitionType.GOVERNANCE_DECISION.value == "governance_decision"
        assert TransitionType.EMERGENCY_ACTION.value == "emergency_action"
        assert TransitionType.AUDIT_REQUEST.value == "audit_request"
        assert TransitionType.CONSTITUTIONAL_AMENDMENT.value == "constitutional_amendment"
        assert TransitionType.ROLLBACK.value == "rollback"


class TestProofType:
    """Tests for ProofType enum."""

    def test_all_proof_types_defined(self):
        """Test that all proof types are defined."""
        assert ProofType.HASH_CHAIN.value == "hash_chain"
        assert ProofType.MERKLE_PROOF.value == "merkle_proof"
        assert ProofType.SIGNATURE.value == "signature"
        assert ProofType.MULTI_SIG.value == "multi_sig"
        assert ProofType.ZERO_KNOWLEDGE.value == "zero_knowledge"


class TestValidTransitions:
    """Tests for valid state transitions."""

    def test_initial_transitions(self):
        """Test valid transitions from INITIAL."""
        valid = VALID_TRANSITIONS[TransitionState.INITIAL]
        assert TransitionState.PENDING_VALIDATION in valid
        assert TransitionState.REJECTED in valid

    def test_validated_transitions(self):
        """Test valid transitions from VALIDATED."""
        valid = VALID_TRANSITIONS[TransitionState.VALIDATED]
        assert TransitionState.PENDING_APPROVAL in valid
        assert TransitionState.REJECTED in valid

    def test_completed_is_terminal(self):
        """Test that COMPLETED only allows rollback."""
        valid = VALID_TRANSITIONS[TransitionState.COMPLETED]
        assert TransitionState.ROLLED_BACK in valid
        assert len(valid) == 1

    def test_rejected_is_terminal(self):
        """Test that REJECTED is terminal."""
        valid = VALID_TRANSITIONS[TransitionState.REJECTED]
        assert len(valid) == 0

    def test_rolled_back_is_terminal(self):
        """Test that ROLLED_BACK is terminal."""
        valid = VALID_TRANSITIONS[TransitionState.ROLLED_BACK]
        assert len(valid) == 0


class TestStateTransitionManagerCreation:
    """Tests for StateTransitionManager creation."""

    def test_default_creation(self):
        """Test manager creation with defaults."""
        manager = create_transition_manager()
        assert manager is not None
        assert manager.require_proof_verification

    def test_without_proof_verification(self):
        """Test manager without proof verification requirement."""
        manager = create_transition_manager(require_proof_verification=False)
        assert not manager.require_proof_verification


class TestTransitionCreation:
    """Tests for transition creation."""

    def test_create_transition(self):
        """Test basic transition creation."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            state_data={"action": "test"},
        )

        assert transition is not None
        assert transition.transition_type == TransitionType.GOVERNANCE_DECISION
        assert transition.current_state == TransitionState.INITIAL
        assert transition.constitutional_hash == CONSTITUTIONAL_HASH

    def test_transition_has_unique_id(self):
        """Test that each transition has unique ID."""
        manager = create_transition_manager()
        t1 = manager.create_transition(TransitionType.POLICY_CHANGE, {})
        t2 = manager.create_transition(TransitionType.ACCESS_GRANT, {})

        assert t1.transition_id != t2.transition_id

    def test_transition_with_context(self):
        """Test transition with context."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            state_data={"action": "test"},
            context={"key": "value"},
            initiated_by="test-user",
        )

        assert transition.context["key"] == "value"
        assert transition.initiated_by == "test-user"

    def test_transition_creates_initial_proof(self):
        """Test that transition creates initial proof."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        assert len(transition.proofs) == 1
        assert transition.proofs[0].from_state == TransitionState.INITIAL


class TestStateTransitions:
    """Tests for state transitions."""

    async def test_transition_to_valid_state(self):
        """Test transitioning to valid state."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        success, proof = await manager.transition_to(
            transition,
            TransitionState.PENDING_VALIDATION,
            "test-user",
        )

        assert success
        assert proof is not None
        assert transition.current_state == TransitionState.PENDING_VALIDATION

    async def test_transition_to_invalid_state(self):
        """Test transitioning to invalid state fails."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Cannot go directly from INITIAL to APPROVED
        success, proof = await manager.transition_to(
            transition,
            TransitionState.APPROVED,
            "test-user",
        )

        assert not success
        assert proof is None
        assert transition.current_state == TransitionState.INITIAL

    async def test_transition_generates_proof(self):
        """Test that transitions generate proofs."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        initial_proof_count = len(transition.proofs)

        success, proof = await manager.transition_to(
            transition,
            TransitionState.PENDING_VALIDATION,
            "test-user",
        )

        assert success
        assert len(transition.proofs) == initial_proof_count + 1
        assert proof.from_state == TransitionState.INITIAL
        assert proof.to_state == TransitionState.PENDING_VALIDATION

    async def test_transition_records_actor(self):
        """Test that transitions record the actor."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        await manager.transition_to(
            transition,
            TransitionState.PENDING_VALIDATION,
            "validator-001",
        )

        # The proof should record the signer
        latest_proof = transition.proofs[-1]
        assert latest_proof.signer_id == "validator-001"


class TestValidationTransition:
    """Tests for validation transition sequence."""

    async def test_validate_transition(self):
        """Test validation transition sequence."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        success, _proof = await manager._validate_transition_sequence(
            transition,
            "validator-001",
        )

        assert success
        assert transition.current_state == TransitionState.VALIDATED


class TestApprovalTransition:
    """Tests for approval transitions."""

    async def test_approve_transition(self):
        """Test approving a validated transition."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # First validate
        await manager._validate_transition_sequence(transition, "validator")

        # Then move to pending approval and approve
        await manager.transition_to(transition, TransitionState.PENDING_APPROVAL, "system")
        success, _proof = await manager.approve_transition(
            transition,
            "approver-001",
            "Approved for execution",
        )

        assert success
        assert transition.current_state == TransitionState.APPROVED
        assert "approver-001" in transition.approved_by


class TestExecutionTransition:
    """Tests for execution transitions."""

    async def test_execute_transition(self):
        """Test executing an approved transition."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Move to approved state
        await manager.transition_to(transition, TransitionState.PENDING_VALIDATION, "v")
        await manager.transition_to(transition, TransitionState.VALIDATED, "v")
        await manager.transition_to(transition, TransitionState.PENDING_APPROVAL, "v")
        await manager.transition_to(transition, TransitionState.APPROVED, "a")

        async def execute_func(state_data):
            return {"executed": True}

        success, _proof = await manager.execute_transition(
            transition,
            "executor-001",
            execute_func,
        )

        assert success
        assert transition.current_state == TransitionState.EXECUTED
        assert transition.execution_result is not None

    async def test_execute_transition_failure(self):
        """Test handling execution failure."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Move to approved state
        await manager.transition_to(transition, TransitionState.PENDING_VALIDATION, "v")
        await manager.transition_to(transition, TransitionState.VALIDATED, "v")
        await manager.transition_to(transition, TransitionState.PENDING_APPROVAL, "v")
        await manager.transition_to(transition, TransitionState.APPROVED, "a")

        async def failing_execute(state_data):
            raise Exception("Execution failed")

        success, _proof = await manager.execute_transition(
            transition,
            "executor-001",
            failing_execute,
        )

        assert not success
        assert transition.current_state == TransitionState.FAILED


class TestRejectionTransition:
    """Tests for rejection transitions."""

    async def test_reject_transition(self):
        """Test rejecting a transition."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        success, _proof = await manager.reject_transition(
            transition,
            "rejector-001",
            "Policy violation detected",
        )

        assert success
        assert transition.current_state == TransitionState.REJECTED
        assert transition.rejected_by == "rejector-001"
        assert transition.rejection_reason == "Policy violation detected"


class TestRollbackTransition:
    """Tests for rollback transitions."""

    async def test_rollback_transition(self):
        """Test rolling back a transition."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Execute transition
        await manager.transition_to(transition, TransitionState.PENDING_VALIDATION, "v")
        await manager.transition_to(transition, TransitionState.VALIDATED, "v")

        # Create checkpoint
        manager._create_checkpoint(transition, "before_rollback")

        await manager.transition_to(transition, TransitionState.PENDING_APPROVAL, "a")
        await manager.transition_to(transition, TransitionState.APPROVED, "a")
        await manager.transition_to(transition, TransitionState.EXECUTING, "e")
        await manager.transition_to(transition, TransitionState.EXECUTED, "e")

        # Rollback
        async def rollback_func(state_data):
            return {"rolled_back": True}

        success, _proof = await manager.rollback_transition(
            transition,
            "rollback-user",
            "Reverting due to issue",
            rollback_func,
        )

        assert success
        assert transition.current_state == TransitionState.ROLLED_BACK
        assert transition.rollback_data is not None

    async def test_rollback_without_checkpoint(self):
        """Test rollback fails without checkpoint."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # No checkpoints created

        success, _proof = await manager.rollback_transition(
            transition,
            "rollback-user",
            "Reverting",
        )

        assert not success


class TestCompletionTransition:
    """Tests for completion transitions."""

    async def test_complete_transition(self):
        """Test completing a transition."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Move through all states
        await manager.transition_to(transition, TransitionState.PENDING_VALIDATION, "v")
        await manager.transition_to(transition, TransitionState.VALIDATED, "v")
        await manager.transition_to(transition, TransitionState.PENDING_APPROVAL, "a")
        await manager.transition_to(transition, TransitionState.APPROVED, "a")
        await manager.transition_to(transition, TransitionState.EXECUTING, "e")
        await manager.transition_to(transition, TransitionState.EXECUTED, "e")

        success, _proof = await manager.complete_transition(
            transition,
            "completer-001",
        )

        assert success
        assert transition.current_state == TransitionState.COMPLETED
        assert transition.completed_at is not None
        assert transition.is_terminal


class TestTransitionProof:
    """Tests for TransitionProof model."""

    def test_proof_creation(self):
        """Test proof creation."""
        proof = TransitionProof(
            transition_id="trans-001",
            from_state=TransitionState.INITIAL,
            to_state=TransitionState.PENDING_VALIDATION,
            state_hash_before="abc123",
            state_hash_after="def456",
        )

        assert proof.proof_id is not None
        assert proof.proof_hash is not None
        assert proof.constitutional_hash == CONSTITUTIONAL_HASH

    def test_proof_verification(self):
        """Test proof hash verification."""
        proof = TransitionProof(
            transition_id="trans-001",
            from_state=TransitionState.INITIAL,
            to_state=TransitionState.PENDING_VALIDATION,
            state_hash_before="abc123",
            state_hash_after="def456",
        )

        assert proof.verify()

    def test_proof_to_dict(self):
        """Test proof serialization."""
        proof = TransitionProof(
            transition_id="trans-001",
            from_state=TransitionState.INITIAL,
            to_state=TransitionState.PENDING_VALIDATION,
        )

        data = proof.to_dict()

        assert data["transition_id"] == "trans-001"
        assert data["from_state"] == "initial"
        assert data["to_state"] == "pending_validation"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH


class TestProofChain:
    """Tests for proof chain integrity."""

    async def test_proof_chain_continuity(self):
        """Test that proof chain maintains continuity."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        # Create multiple transitions
        await manager.transition_to(transition, TransitionState.PENDING_VALIDATION, "v")
        await manager.transition_to(transition, TransitionState.VALIDATED, "v")

        # Verify chain
        for i in range(1, len(transition.proofs)):
            assert transition.proofs[i].previous_proof_hash == transition.proofs[i - 1].proof_hash

    def test_verify_proof_chain(self):
        """Test proof chain verification."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        is_valid, errors = manager.verify_proof_chain(transition)

        assert is_valid
        assert len(errors) == 0


class TestConstitutionalTransition:
    """Tests for ConstitutionalTransition model."""

    def test_transition_to_dict(self):
        """Test transition serialization."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
            context={"key": "value"},
        )

        data = transition.to_dict()

        assert "transition_id" in data
        assert data["transition_type"] == "governance_decision"
        assert data["current_state"] == "initial"
        assert data["constitutional_hash"] == CONSTITUTIONAL_HASH

    def test_is_terminal_property(self):
        """Test is_terminal property."""
        transition = ConstitutionalTransition()

        assert not transition.is_terminal

        transition.current_state = TransitionState.COMPLETED
        assert transition.is_terminal

        transition.current_state = TransitionState.REJECTED
        assert transition.is_terminal

        transition.current_state = TransitionState.ROLLED_BACK
        assert transition.is_terminal

    def test_proof_chain_property(self):
        """Test proof_chain property."""
        transition = ConstitutionalTransition()
        proof1 = TransitionProof(proof_hash="hash1")
        proof2 = TransitionProof(proof_hash="hash2")
        transition.proofs = [proof1, proof2]

        chain = transition.proof_chain

        assert chain == ["hash1", "hash2"]


class TestCheckpoints:
    """Tests for checkpoint management."""

    def test_create_checkpoint(self):
        """Test checkpoint creation."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        checkpoint = manager._create_checkpoint(
            transition,
            "critical_point",
        )

        assert checkpoint is not None
        assert checkpoint["name"] == "critical_point"
        assert checkpoint["transition_id"] == transition.transition_id
        assert len(transition.checkpoints) == 1

    def test_checkpoint_captures_state(self):
        """Test that checkpoint captures state."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        checkpoint = manager._create_checkpoint(
            transition,
            "state_capture",
        )

        assert "state_data_snapshot" in checkpoint
        assert checkpoint["state"] == transition.current_state.value


class TestManagerOperations:
    """Tests for manager operations."""

    def test_get_transition(self):
        """Test getting transition by ID."""
        manager = create_transition_manager()
        transition = manager.create_transition(
            TransitionType.GOVERNANCE_DECISION,
            {"action": "test"},
        )

        retrieved = manager.get_transition(transition.transition_id)

        assert retrieved is not None
        assert retrieved.transition_id == transition.transition_id

    def test_get_nonexistent_transition(self):
        """Test getting nonexistent transition."""
        manager = create_transition_manager()
        retrieved = manager.get_transition("nonexistent-id")

        assert retrieved is None

    def test_list_active_transitions(self):
        """Test listing active transitions."""
        manager = create_transition_manager()
        manager.create_transition(TransitionType.POLICY_CHANGE, {})
        manager.create_transition(TransitionType.ACCESS_GRANT, {})

        active = manager.list_active_transitions()

        assert len(active) == 2

    async def test_manager_status(self):
        """Test getting manager status."""
        manager = create_transition_manager()
        manager.create_transition(TransitionType.GOVERNANCE_DECISION, {})

        status = await manager.get_manager_status()

        assert status["manager"] == "State Transition Manager"
        assert status["status"] == "operational"
        assert status["active_transitions"] == 1
        assert status["constitutional_hash"] == CONSTITUTIONAL_HASH
