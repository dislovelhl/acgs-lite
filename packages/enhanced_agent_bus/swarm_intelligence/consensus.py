"""
Swarm Intelligence - Consensus Mechanism

Byzantine fault-tolerant consensus for distributed decision-making.

Constitutional Hash: 608508a9bd224290
"""

from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

try:
    from enhanced_agent_bus._compat.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

from .enums import ConsensusType
from .models import ConsensusProposal

logger = get_logger(__name__)

# Configuration constants
DEFAULT_MAX_FAULTY_VOTERS = 1000
DEFAULT_MAX_COMPLETED_PROPOSALS = 10000


class ConsensusMechanism:
    """
    Byzantine fault-tolerant consensus mechanism v3.1.

    Enhanced with:
    - Timeout recovery with automatic vote resolution
    - Byzantine fault detection and conflict tracking
    - Proposal expiration and cleanup
    - Faulty voter identification and blacklisting

    Supports multiple consensus types for distributed decision-making.
    """

    def __init__(
        self,
        max_proposal_age_minutes: int = 60,
        max_faulty_voters: int = DEFAULT_MAX_FAULTY_VOTERS,
        max_completed_proposals: int = DEFAULT_MAX_COMPLETED_PROPOSALS,
    ):
        self._proposals: dict[str, ConsensusProposal] = {}
        self._thresholds = {
            ConsensusType.MAJORITY: 0.5,
            ConsensusType.SUPERMAJORITY: 0.67,
            ConsensusType.UNANIMOUS: 1.0,
            ConsensusType.QUORUM: 0.33,
        }
        self._faulty_voters: OrderedDict[str, list[str]] = (
            OrderedDict()
        )  # voter_id -> [proposal_ids]
        self._max_proposal_age_minutes = max_proposal_age_minutes
        self._max_faulty_voters = max_faulty_voters
        self._completed_proposals: OrderedDict[str, datetime] = (
            OrderedDict()
        )  # proposal_id -> completed_at
        self._max_completed_proposals = max_completed_proposals

    async def create_proposal(
        self,
        proposer_id: str,
        action: str,
        context: JSONDict,
        consensus_type: ConsensusType = ConsensusType.MAJORITY,
        timeout_seconds: int = 30,
    ) -> ConsensusProposal:
        """Create a new consensus proposal with cleanup of old proposals."""
        # Cleanup old proposals before creating new one
        await self._cleanup_expired_proposals()

        proposal = ConsensusProposal(
            id=str(uuid4()),
            proposer_id=proposer_id,
            action=action,
            context=context,
            required_type=consensus_type,
            deadline=datetime.now(UTC) + timedelta(seconds=timeout_seconds),
        )
        self._proposals[proposal.id] = proposal
        logger.info(
            f"Created proposal {proposal.id[:8]}... (type={consensus_type.value}, timeout={timeout_seconds}s)"
        )
        return proposal

    async def vote(
        self,
        proposal_id: str,
        voter_id: str,
        approve: bool,
    ) -> bool:
        """Cast a vote on a proposal with Byzantine fault detection."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return False

        current_time = datetime.now(UTC)

        # Check if proposal is expired
        if current_time > proposal.deadline:
            logger.warning(f"Vote rejected: proposal {proposal_id[:8]}... has expired")
            return False

        # Check for conflicting votes (Byzantine fault detection)
        if voter_id in proposal.votes:
            existing_vote = proposal.votes[voter_id]
            if existing_vote != approve:
                # Byzantine fault: voter changed their vote
                if voter_id not in self._faulty_voters:
                    self._faulty_voters[voter_id] = []
                if proposal_id not in self._faulty_voters[voter_id]:
                    self._faulty_voters[voter_id].append(proposal_id)
                    self._trim_faulty_voters()
                    logger.warning(
                        f"Byzantine fault detected: voter {voter_id} changed vote on proposal {proposal_id[:8]}..."
                    )
                return False

        proposal.votes[voter_id] = approve
        logger.debug(f"Vote cast on proposal {proposal_id[:8]}... by voter {voter_id}: {approve}")
        return True

    def check_consensus(
        self,
        proposal_id: str,
        total_voters: int,
        timeout_recovery: bool = True,
    ) -> tuple[bool, bool | None]:
        """
        Check if consensus has been reached with optional timeout recovery.

        Args:
            proposal_id: The proposal to check
            total_voters: Total number of eligible voters
            timeout_recovery: If True, auto-resolve on timeout with default=False

        Returns:
            Tuple of (is_decided, result)
            - is_decided: Whether a decision has been made
            - result: The decision (True/False) or None if undecided
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return (False, None)

        if total_voters == 0:
            return (False, None)

        current_time = datetime.now(UTC)
        is_expired = current_time > proposal.deadline

        votes_cast = len(proposal.votes)
        approvals = sum(1 for v in proposal.votes.values() if v)
        rejections = votes_cast - approvals

        threshold = self._thresholds[proposal.required_type]
        required_votes = int(total_voters * threshold) + 1

        # Check for successful consensus
        if approvals >= required_votes:
            proposal.result = True
            proposal.completed_at = current_time
            self._completed_proposals[proposal_id] = current_time
            self._trim_completed_proposals()
            logger.info(
                f"Consensus reached (APPROVED) on proposal {proposal_id[:8]}... ({approvals}/{total_voters} votes)"
            )
            return (True, True)

        # Check if consensus is impossible
        if rejections >= (total_voters - required_votes + 1):
            proposal.result = False
            proposal.completed_at = current_time
            self._completed_proposals[proposal_id] = current_time
            self._trim_completed_proposals()
            logger.info(
                f"Consensus reached (REJECTED) on proposal {proposal_id[:8]}... ({rejections} rejections)"
            )
            return (True, False)

        # Timeout recovery: if expired and no consensus, apply default
        if is_expired and timeout_recovery:
            proposal.result = False  # Default to rejection on timeout
            proposal.completed_at = current_time
            self._completed_proposals[proposal_id] = current_time
            self._trim_completed_proposals()
            logger.warning(
                f"Consensus timeout on proposal {proposal_id[:8]}... ({votes_cast}/{total_voters} votes cast)"
            )
            return (True, False)

        return (False, None)

    async def force_resolve(
        self,
        proposal_id: str,
        default_result: bool = False,
    ) -> bool | None:
        """Forcefully resolve a proposal with a default result."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return None

        current_time = datetime.now(UTC)
        proposal.result = default_result
        proposal.completed_at = current_time
        self._completed_proposals[proposal_id] = current_time
        self._trim_completed_proposals()

        logger.info(f"Forced resolution on proposal {proposal_id[:8]}...: {default_result}")
        return default_result

    async def _cleanup_expired_proposals(self) -> int:
        """Remove old completed proposals to prevent memory leaks."""
        current_time = datetime.now(UTC)
        expired_ids = []

        for proposal_id, completed_time in list(self._completed_proposals.items()):
            age_minutes = (current_time - completed_time).total_seconds() / 60
            if age_minutes > self._max_proposal_age_minutes:
                expired_ids.append(proposal_id)

        for proposal_id in expired_ids:
            if proposal_id in self._proposals:
                del self._proposals[proposal_id]
            del self._completed_proposals[proposal_id]

        if expired_ids:
            logger.debug(f"Cleaned up {len(expired_ids)} expired proposals")

        return len(expired_ids)

    def _trim_faulty_voters(self) -> None:
        """
        Trim faulty voters when exceeding max size.

        Removes oldest entries (FIFO) when the collection exceeds the limit.
        """
        if len(self._faulty_voters) > self._max_faulty_voters:
            excess = len(self._faulty_voters) - self._max_faulty_voters
            for _ in range(excess):
                self._faulty_voters.popitem(last=False)
            logger.warning(
                f"Faulty voters trimmed: removed {excess} oldest entries "
                f"(limit: {self._max_faulty_voters})"
            )

    def _trim_completed_proposals(self) -> None:
        """
        Trim completed proposals when exceeding max size.

        Removes oldest entries (FIFO) when the collection exceeds the limit.
        """
        if len(self._completed_proposals) > self._max_completed_proposals:
            excess = len(self._completed_proposals) - self._max_completed_proposals
            for _ in range(excess):
                self._completed_proposals.popitem(last=False)
            logger.warning(
                f"Completed proposals trimmed: removed {excess} oldest entries "
                f"(limit: {self._max_completed_proposals})"
            )

    def get_faulty_voters(self) -> dict[str, list[str]]:
        """Get map of voters who exhibited Byzantine faults."""
        return dict(self._faulty_voters)

    def get_proposal(self, proposal_id: str) -> ConsensusProposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def get_proposal_stats(self) -> JSONDict:
        """Get statistics about current proposals."""
        active = [p for p in self._proposals.values() if p.result is None]
        completed = [p for p in self._proposals.values() if p.result is not None]

        return {
            "total_proposals": len(self._proposals),
            "active_proposals": len(active),
            "completed_proposals": len(completed),
            "faulty_voters": len(self._faulty_voters),
            "expired_proposals": len(self._completed_proposals),
        }


__all__ = [
    "ConsensusMechanism",
]
