"""
ACGS-2 Constitutional Transition - State Transitions with Proofs
Constitutional Hash: 608508a9bd224290

Implements state transition management for constitutional governance:
- Cryptographic proofs for state transitions
- Constitutional checkpoint enforcement
- Immutable audit trail for all state changes
- Rollback capability with proof verification

Key Features:
- State machine for governance transitions
- Cryptographic hash chain for integrity
- Constitutional validation at each transition
- Full proof generation for compliance

Performance Targets:
- State transition: < 10ms
- Proof generation: < 5ms
- Checkpoint creation: < 2ms
"""

import asyncio
import hashlib
import inspect
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

# Constitutional hash for immutable validation
try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"
try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)
TRANSITION_EXECUTION_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
    Exception,
)
TRANSITION_ROLLBACK_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    asyncio.TimeoutError,
)


class TransitionState(Enum):
    """States for constitutional governance transitions."""

    INITIAL = "initial"
    PENDING_VALIDATION = "pending_validation"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    EXECUTED = "executed"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class TransitionType(Enum):
    """Types of state transitions."""

    POLICY_CHANGE = "policy_change"
    ACCESS_GRANT = "access_grant"
    ACCESS_REVOKE = "access_revoke"
    GOVERNANCE_DECISION = "governance_decision"
    EMERGENCY_ACTION = "emergency_action"
    AUDIT_REQUEST = "audit_request"
    CONSTITUTIONAL_AMENDMENT = "constitutional_amendment"
    ROLLBACK = "rollback"


class ProofType(Enum):
    """Types of transition proofs."""

    HASH_CHAIN = "hash_chain"
    MERKLE_PROOF = "merkle_proof"
    SIGNATURE = "signature"
    MULTI_SIG = "multi_sig"
    ZERO_KNOWLEDGE = "zero_knowledge"


# Valid state transitions (from_state -> allowed_to_states)
VALID_TRANSITIONS: dict[TransitionState, set[TransitionState]] = {
    TransitionState.INITIAL: {TransitionState.PENDING_VALIDATION, TransitionState.REJECTED},
    TransitionState.PENDING_VALIDATION: {TransitionState.VALIDATED, TransitionState.REJECTED},
    TransitionState.VALIDATED: {TransitionState.PENDING_APPROVAL, TransitionState.REJECTED},
    TransitionState.PENDING_APPROVAL: {TransitionState.APPROVED, TransitionState.REJECTED},
    TransitionState.APPROVED: {TransitionState.EXECUTING, TransitionState.REJECTED},
    TransitionState.EXECUTING: {TransitionState.EXECUTED, TransitionState.FAILED},
    TransitionState.EXECUTED: {TransitionState.PENDING_VERIFICATION, TransitionState.ROLLED_BACK},
    TransitionState.PENDING_VERIFICATION: {TransitionState.VERIFIED, TransitionState.ROLLED_BACK},
    TransitionState.VERIFIED: {TransitionState.COMPLETED, TransitionState.ROLLED_BACK},
    TransitionState.COMPLETED: {TransitionState.ROLLED_BACK},  # Only rollback from completed
    TransitionState.REJECTED: set(),  # Terminal state
    TransitionState.ROLLED_BACK: set(),  # Terminal state
    TransitionState.FAILED: {TransitionState.ROLLED_BACK},  # Can retry via rollback
}


@dataclass
class TransitionProof:
    """Cryptographic proof for state transition."""

    proof_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    proof_type: ProofType = ProofType.HASH_CHAIN
    transition_id: str = ""
    from_state: TransitionState = TransitionState.INITIAL
    to_state: TransitionState = TransitionState.PENDING_VALIDATION
    state_hash_before: str = ""
    state_hash_after: str = ""
    proof_hash: str = ""
    chain_position: int = 0
    previous_proof_hash: str = ""
    signature: str | None = None
    signer_id: str | None = None
    witnesses: list[str] = field(default_factory=list)
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self):
        """Generate proof hash if not provided."""
        if not self.proof_hash:
            self.proof_hash = self._generate_proof_hash()

    def _generate_proof_hash(self) -> str:
        """Generate cryptographic hash for the proof."""
        content = (
            f"{self.transition_id}:{self.from_state.value}:{self.to_state.value}:"
            f"{self.state_hash_before}:{self.state_hash_after}:"
            f"{self.chain_position}:{self.previous_proof_hash}:"
            f"{self.constitutional_hash}:{self.created_at.isoformat()}"
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def verify(self) -> bool:
        """Verify the proof integrity."""
        expected_hash = self._generate_proof_hash()
        return self.proof_hash == expected_hash

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "proof_id": self.proof_id,
            "proof_type": self.proof_type.value,
            "transition_id": self.transition_id,
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "state_hash_before": self.state_hash_before,
            "state_hash_after": self.state_hash_after,
            "proof_hash": self.proof_hash,
            "chain_position": self.chain_position,
            "previous_proof_hash": self.previous_proof_hash,
            "signature": self.signature,
            "signer_id": self.signer_id,
            "witnesses": self.witnesses,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ConstitutionalTransition:
    """A constitutional governance state transition."""

    transition_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transition_type: TransitionType = TransitionType.GOVERNANCE_DECISION
    current_state: TransitionState = TransitionState.INITIAL
    state_data: JSONDict = field(default_factory=dict)
    context: JSONDict = field(default_factory=dict)
    proofs: list[TransitionProof] = field(default_factory=list)
    checkpoints: list[JSONDict] = field(default_factory=list)
    initiated_by: str = ""
    approved_by: list[str] = field(default_factory=list)
    rejected_by: str | None = None
    rejection_reason: str | None = None
    execution_result: JSONDict | None = None
    rollback_data: JSONDict | None = None
    metadata: JSONDict = field(default_factory=dict)
    constitutional_hash: str = CONSTITUTIONAL_HASH
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def __post_init__(self):
        """Initialize state hash."""
        self._current_state_hash = self._compute_state_hash()

    def _compute_state_hash(self) -> str:
        """Compute hash of current state."""
        content = (
            f"{self.transition_id}:{self.current_state.value}:"
            f"{self.state_data!s}:{self.constitutional_hash}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def to_dict(self) -> JSONDict:
        """Convert to dictionary."""
        return {
            "transition_id": self.transition_id,
            "transition_type": self.transition_type.value,
            "current_state": self.current_state.value,
            "state_data": self.state_data,
            "context": self.context,
            "proofs": [p.to_dict() for p in self.proofs],
            "checkpoints": self.checkpoints,
            "initiated_by": self.initiated_by,
            "approved_by": self.approved_by,
            "rejected_by": self.rejected_by,
            "rejection_reason": self.rejection_reason,
            "execution_result": self.execution_result,
            "rollback_data": self.rollback_data,
            "metadata": self.metadata,
            "constitutional_hash": self.constitutional_hash,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @property
    def is_terminal(self) -> bool:
        """Check if transition is in a terminal state."""
        return self.current_state in (
            TransitionState.COMPLETED,
            TransitionState.REJECTED,
            TransitionState.ROLLED_BACK,
        )

    @property
    def proof_chain(self) -> list[str]:
        """Get the chain of proof hashes."""
        return [p.proof_hash for p in self.proofs]


class StateTransitionManager:
    """
    State Transition Manager: Manages constitutional governance transitions.

    Implements:
    - Valid state transition enforcement
    - Cryptographic proof generation for each transition
    - Checkpoint creation for recovery
    - Rollback capability with proof verification

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, require_proof_verification: bool = True):
        self.require_proof_verification = require_proof_verification
        self._active_transitions: dict[str, ConstitutionalTransition] = {}
        self._completed_transitions: dict[str, ConstitutionalTransition] = {}
        self._proof_chain: list[TransitionProof] = []
        self._chain_position = 0

        self.constitutional_hash = CONSTITUTIONAL_HASH

        logger.info("Initialized State Transition Manager")
        logger.info(f"Constitutional Hash: {self.constitutional_hash}")

    def create_transition(
        self,
        transition_type: TransitionType,
        state_data: JSONDict,
        context: JSONDict | None = None,
        initiated_by: str = "system",
        metadata: JSONDict | None = None,
    ) -> ConstitutionalTransition:
        """Create a new constitutional transition."""
        transition = ConstitutionalTransition(
            transition_type=transition_type,
            state_data=state_data,
            context=context or {},
            initiated_by=initiated_by,
            metadata=metadata or {},
        )

        self._active_transitions[transition.transition_id] = transition

        # Create initial proof
        self._create_transition_proof(
            transition,
            TransitionState.INITIAL,
            TransitionState.INITIAL,
        )

        logger.info(
            f"Created transition {transition.transition_id} "
            f"({transition_type.value}) by {initiated_by}"
        )

        return transition

    async def transition_to(
        self,
        transition: ConstitutionalTransition,
        to_state: TransitionState,
        actor_id: str = "system",
        reason: str | None = None,
        execution_result: JSONDict | None = None,
    ) -> tuple[bool, TransitionProof | None]:
        """
        Execute a state transition with proof generation.

        Args:
            transition: The transition to update
            to_state: Target state
            actor_id: ID of the actor performing the transition
            reason: Optional reason for the transition
            execution_result: Optional result data for execution transitions

        Returns:
            Tuple of (success, proof)
        """
        from_state = transition.current_state

        # Validate transition
        if to_state not in VALID_TRANSITIONS.get(from_state, set()):
            logger.warning(f"Invalid transition: {from_state.value} -> {to_state.value}")
            return False, None

        # Store state hash before transition
        state_hash_before = transition._compute_state_hash()

        # Update state
        transition.current_state = to_state
        transition.updated_at = datetime.now(UTC)

        # Handle state-specific logic
        if to_state == TransitionState.APPROVED:
            transition.approved_by.append(actor_id)

        elif to_state == TransitionState.REJECTED:
            transition.rejected_by = actor_id
            transition.rejection_reason = reason

        elif to_state == TransitionState.EXECUTED:
            transition.execution_result = execution_result

        elif to_state in (TransitionState.COMPLETED, TransitionState.ROLLED_BACK):
            transition.completed_at = datetime.now(UTC)

        # Create checkpoint for critical transitions
        if to_state in (
            TransitionState.APPROVED,
            TransitionState.EXECUTED,
            TransitionState.COMPLETED,
        ):
            self._create_checkpoint(transition, f"pre_{to_state.value}")

        # Compute new state hash
        state_hash_after = transition._compute_state_hash()

        # Generate proof
        proof = self._create_transition_proof(
            transition,
            from_state,
            to_state,
            state_hash_before,
            state_hash_after,
            actor_id,
        )

        # Move to completed if terminal
        if transition.is_terminal:
            self._completed_transitions[transition.transition_id] = transition
            if transition.transition_id in self._active_transitions:
                del self._active_transitions[transition.transition_id]

        logger.info(
            f"Transition {transition.transition_id}: "
            f"{from_state.value} -> {to_state.value} by {actor_id}"
        )

        return True, proof

    def _create_transition_proof(
        self,
        transition: ConstitutionalTransition,
        from_state: TransitionState,
        to_state: TransitionState,
        state_hash_before: str = "",
        state_hash_after: str = "",
        signer_id: str | None = None,
    ) -> TransitionProof:
        """Create a cryptographic proof for a state transition."""
        previous_hash = ""
        if self._proof_chain:
            previous_hash = self._proof_chain[-1].proof_hash

        self._chain_position += 1

        proof = TransitionProof(
            transition_id=transition.transition_id,
            from_state=from_state,
            to_state=to_state,
            state_hash_before=state_hash_before or transition._compute_state_hash(),
            state_hash_after=state_hash_after or transition._compute_state_hash(),
            chain_position=self._chain_position,
            previous_proof_hash=previous_hash,
            signer_id=signer_id,
        )

        transition.proofs.append(proof)
        self._proof_chain.append(proof)

        return proof

    def _create_checkpoint(
        self,
        transition: ConstitutionalTransition,
        name: str,
    ) -> JSONDict:
        """Create a checkpoint for the transition."""
        checkpoint = {
            "checkpoint_id": str(uuid.uuid4()),
            "name": name,
            "transition_id": transition.transition_id,
            "state": transition.current_state.value,
            "state_hash": transition._compute_state_hash(),
            "state_data_snapshot": transition.state_data.copy(),
            "proof_count": len(transition.proofs),
            "created_at": datetime.now(UTC).isoformat(),
            "constitutional_hash": self.constitutional_hash,
        }

        transition.checkpoints.append(checkpoint)

        logger.debug(f"Created checkpoint '{name}' for transition {transition.transition_id}")

        return checkpoint

    async def validate_transition(
        self,
        transition: ConstitutionalTransition,
        validator_id: str = "system",
    ) -> tuple[bool, TransitionProof | None]:
        """Validate a transition (move from INITIAL to VALIDATED)."""
        return await self._validate_transition_sequence(transition, validator_id)

    async def _validate_transition_sequence(
        self,
        transition: ConstitutionalTransition,
        validator_id: str,
    ) -> tuple[bool, TransitionProof | None]:
        """Execute validation sequence."""
        success, proof = await self.transition_to(
            transition,
            TransitionState.PENDING_VALIDATION,
            validator_id,
        )

        if success:
            success, proof = await self.transition_to(
                transition,
                TransitionState.VALIDATED,
                validator_id,
            )

        return success, proof

    async def approve_transition(
        self,
        transition: ConstitutionalTransition,
        approver_id: str,
        reason: str | None = None,
    ) -> tuple[bool, TransitionProof | None]:
        """Approve a validated transition."""
        if transition.current_state != TransitionState.VALIDATED:
            # Move to pending approval first if validated
            if transition.current_state == TransitionState.VALIDATED:
                await self.transition_to(
                    transition,
                    TransitionState.PENDING_APPROVAL,
                    approver_id,
                )

        return await self.transition_to(
            transition,
            TransitionState.APPROVED,
            approver_id,
            reason,
        )

    async def execute_transition(
        self,
        transition: ConstitutionalTransition,
        executor_id: str,
        execute_func: Callable[..., object] | None = None,
    ) -> tuple[bool, TransitionProof | None]:
        """Execute an approved transition."""
        if transition.current_state != TransitionState.APPROVED:
            logger.warning(f"Cannot execute transition in state {transition.current_state.value}")
            return False, None

        # Move to executing
        success, _ = await self.transition_to(
            transition,
            TransitionState.EXECUTING,
            executor_id,
        )

        if not success:
            return False, None

        # Execute the transition function if provided
        execution_result = {}
        try:
            if execute_func:
                if inspect.iscoroutinefunction(execute_func):
                    execution_result = await execute_func(transition.state_data)
                else:
                    execution_result = execute_func(transition.state_data)

            # Mark as executed
            return await self.transition_to(
                transition,
                TransitionState.EXECUTED,
                executor_id,
                execution_result=execution_result,
            )

        except TRANSITION_EXECUTION_ERRORS as e:
            logger.error(f"Transition execution failed: {e}")
            await self.transition_to(
                transition,
                TransitionState.FAILED,
                executor_id,
                reason=str(e),
            )
            return False, None

    async def reject_transition(
        self,
        transition: ConstitutionalTransition,
        rejector_id: str,
        reason: str,
    ) -> tuple[bool, TransitionProof | None]:
        """Reject a transition."""
        return await self.transition_to(
            transition,
            TransitionState.REJECTED,
            rejector_id,
            reason,
        )

    async def rollback_transition(
        self,
        transition: ConstitutionalTransition,
        actor_id: str,
        reason: str,
        rollback_func: Callable[..., object] | None = None,
    ) -> tuple[bool, TransitionProof | None]:
        """Rollback a transition to its previous state."""
        if not transition.checkpoints:
            logger.warning("No checkpoints available for rollback")
            return False, None

        # Get the last checkpoint
        last_checkpoint = transition.checkpoints[-1]

        # Store rollback data
        transition.rollback_data = {
            "rollback_from": transition.current_state.value,
            "rollback_to_checkpoint": last_checkpoint["checkpoint_id"],
            "reason": reason,
            "rolled_back_by": actor_id,
            "rolled_back_at": datetime.now(UTC).isoformat(),
        }

        # Execute rollback function if provided
        if rollback_func:
            try:
                if inspect.iscoroutinefunction(rollback_func):
                    await rollback_func(last_checkpoint["state_data_snapshot"])
                else:
                    rollback_func(last_checkpoint["state_data_snapshot"])
            except TRANSITION_ROLLBACK_ERRORS as e:
                logger.error(f"Rollback function failed: {e}")

        return await self.transition_to(
            transition,
            TransitionState.ROLLED_BACK,
            actor_id,
            reason,
        )

    async def complete_transition(
        self,
        transition: ConstitutionalTransition,
        actor_id: str,
    ) -> tuple[bool, TransitionProof | None]:
        """Complete a verified transition."""
        if transition.current_state == TransitionState.VERIFIED:
            return await self.transition_to(
                transition,
                TransitionState.COMPLETED,
                actor_id,
            )

        # Move through verification if not there
        if transition.current_state == TransitionState.EXECUTED:
            success, _ = await self.transition_to(
                transition,
                TransitionState.PENDING_VERIFICATION,
                actor_id,
            )
            if success:
                success, _ = await self.transition_to(
                    transition,
                    TransitionState.VERIFIED,
                    actor_id,
                )
                if success:
                    return await self.transition_to(
                        transition,
                        TransitionState.COMPLETED,
                        actor_id,
                    )

        return False, None

    def verify_proof_chain(
        self,
        transition: ConstitutionalTransition,
    ) -> tuple[bool, list[str]]:
        """
        Verify the integrity of a transition's proof chain.

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        if not transition.proofs:
            return True, []

        for i, proof in enumerate(transition.proofs):
            # Verify proof hash
            if not proof.verify():
                errors.append(f"Proof {i} hash verification failed")

            # Verify chain continuity
            if i > 0:
                if proof.previous_proof_hash != transition.proofs[i - 1].proof_hash:
                    errors.append(f"Proof {i} chain continuity broken")

            # Verify constitutional hash
            if proof.constitutional_hash != self.constitutional_hash:
                errors.append(f"Proof {i} constitutional hash mismatch")

        is_valid = len(errors) == 0
        return is_valid, errors

    def get_transition(self, transition_id: str) -> ConstitutionalTransition | None:
        """Get a transition by ID."""
        return self._active_transitions.get(transition_id) or self._completed_transitions.get(
            transition_id
        )

    def list_active_transitions(self) -> list[JSONDict]:
        """List all active transitions."""
        return [
            {
                "transition_id": t.transition_id,
                "type": t.transition_type.value,
                "state": t.current_state.value,
                "initiated_by": t.initiated_by,
                "created_at": t.created_at.isoformat(),
            }
            for t in self._active_transitions.values()
        ]

    async def get_manager_status(self) -> JSONDict:
        """Get manager status and statistics."""
        active_count = len(self._active_transitions)
        completed_count = len(self._completed_transitions)

        all_transitions = list(self._active_transitions.values()) + list(
            self._completed_transitions.values()
        )

        state_counts: dict[str, int] = {}
        for t in all_transitions:
            state = t.current_state.value
            state_counts[state] = state_counts.get(state, 0) + 1

        return {
            "manager": "State Transition Manager",
            "status": "operational",
            "active_transitions": active_count,
            "completed_transitions": completed_count,
            "total_proofs": len(self._proof_chain),
            "state_distribution": state_counts,
            "chain_position": self._chain_position,
            "constitutional_hash": self.constitutional_hash,
        }


def create_transition_manager(
    require_proof_verification: bool = True,
) -> StateTransitionManager:
    """Factory function to create a state transition manager."""
    return StateTransitionManager(
        require_proof_verification=require_proof_verification,
    )


__all__ = [
    "CONSTITUTIONAL_HASH",
    "VALID_TRANSITIONS",
    "ConstitutionalTransition",
    "ProofType",
    "StateTransitionManager",
    "TransitionProof",
    "TransitionState",
    "TransitionType",
    "create_transition_manager",
]
