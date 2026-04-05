"""
ACGS-2 Enhanced Agent Bus - Voting Service Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the deliberation layer voting service.
"""

from datetime import UTC, datetime, timezone

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.deliberation_layer.voting_service import (
    Election,
    Vote,
    VotingService,
    VotingStrategy,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def valid_message() -> AgentMessage:
    """Create a valid test message."""
    return AgentMessage(
        from_agent="test-sender",
        to_agent="test-receiver",
        content={"action": "test", "data": "hello"},
        constitutional_hash=CONSTITUTIONAL_HASH,
    )


@pytest.fixture
def voting_service() -> VotingService:
    """Create a voting service with default settings (in-memory for testing)."""
    return VotingService(force_in_memory=True)


@pytest.fixture
def quorum_voting_service() -> VotingService:
    """Create a voting service with quorum strategy (in-memory for testing)."""
    return VotingService(default_strategy=VotingStrategy.QUORUM, force_in_memory=True)


@pytest.fixture
def unanimous_voting_service() -> VotingService:
    """Create a voting service with unanimous strategy (in-memory for testing)."""
    return VotingService(default_strategy=VotingStrategy.UNANIMOUS, force_in_memory=True)


@pytest.fixture
def super_majority_voting_service() -> VotingService:
    """Create a voting service with super majority strategy (in-memory for testing)."""
    return VotingService(default_strategy=VotingStrategy.SUPER_MAJORITY, force_in_memory=True)


# =============================================================================
# VotingStrategy Tests
# =============================================================================


class TestVotingStrategy:
    """Tests for VotingStrategy enum."""

    def test_quorum_value(self) -> None:
        """Test quorum strategy value."""
        assert VotingStrategy.QUORUM.value == "quorum"

    def test_unanimous_value(self) -> None:
        """Test unanimous strategy value."""
        assert VotingStrategy.UNANIMOUS.value == "unanimous"

    def test_super_majority_value(self) -> None:
        """Test super majority strategy value."""
        assert VotingStrategy.SUPER_MAJORITY.value == "super-majority"

    def test_enum_members(self) -> None:
        """Test all enum members exist."""
        members = list(VotingStrategy)
        assert len(members) == 3
        assert VotingStrategy.QUORUM in members
        assert VotingStrategy.UNANIMOUS in members
        assert VotingStrategy.SUPER_MAJORITY in members


# =============================================================================
# Vote Tests
# =============================================================================


class TestVote:
    """Tests for Vote dataclass."""

    def test_create_approve_vote(self) -> None:
        """Test creating an approval vote."""
        vote = Vote(agent_id="agent-1", decision="APPROVE", reason="Looks good")
        assert vote.agent_id == "agent-1"
        assert vote.decision == "APPROVE"
        assert vote.reason == "Looks good"
        assert vote.timestamp is not None

    def test_create_deny_vote(self) -> None:
        """Test creating a deny vote."""
        vote = Vote(agent_id="agent-2", decision="DENY", reason="Policy violation")
        assert vote.agent_id == "agent-2"
        assert vote.decision == "DENY"
        assert vote.reason == "Policy violation"

    def test_create_abstain_vote(self) -> None:
        """Test creating an abstain vote."""
        vote = Vote(agent_id="agent-3", decision="ABSTAIN")
        assert vote.decision == "ABSTAIN"
        assert vote.reason is None

    def test_vote_timestamp_auto_generated(self) -> None:
        """Test that timestamp is automatically generated."""
        vote = Vote(agent_id="agent-1", decision="APPROVE")
        assert isinstance(vote.timestamp, datetime)
        # Should be recent (within last 5 seconds)
        now = datetime.now(UTC)
        delta = now - vote.timestamp
        assert delta.total_seconds() < 5


# =============================================================================
# Election Tests
# =============================================================================


class TestElection:
    """Tests for Election dataclass."""

    def test_create_election(self) -> None:
        """Test creating an election."""
        election = Election(
            election_id="election-123",
            message_id="msg-456",
            strategy=VotingStrategy.QUORUM,
            participants={"agent-1", "agent-2", "agent-3"},
        )
        assert election.election_id == "election-123"
        assert election.message_id == "msg-456"
        assert election.strategy == VotingStrategy.QUORUM
        assert len(election.participants) == 3
        assert election.status == "OPEN"
        assert election.votes == {}

    def test_election_default_status(self) -> None:
        """Test election default status is OPEN."""
        election = Election(
            election_id="e1",
            message_id="m1",
            strategy=VotingStrategy.UNANIMOUS,
            participants={"a1"},
        )
        assert election.status == "OPEN"

    def test_election_created_at_auto_generated(self) -> None:
        """Test that created_at is automatically generated."""
        election = Election(
            election_id="e1", message_id="m1", strategy=VotingStrategy.QUORUM, participants={"a1"}
        )
        assert isinstance(election.created_at, datetime)

    def test_election_expires_at_default_none(self) -> None:
        """Test expires_at defaults to None."""
        election = Election(
            election_id="e1", message_id="m1", strategy=VotingStrategy.QUORUM, participants={"a1"}
        )
        assert election.expires_at is None


# =============================================================================
# VotingService Tests
# =============================================================================


class TestVotingService:
    """Tests for VotingService class."""

    def test_create_service_default_strategy(self) -> None:
        """Test creating service with default strategy."""
        service = VotingService()
        assert service.default_strategy == VotingStrategy.QUORUM
        assert service.elections == {}

    def test_create_service_custom_strategy(self) -> None:
        """Test creating service with custom strategy."""
        service = VotingService(default_strategy=VotingStrategy.UNANIMOUS)
        assert service.default_strategy == VotingStrategy.UNANIMOUS

    async def test_create_election(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test creating an election."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await voting_service.create_election(valid_message, participants, timeout=30)

        assert election_id is not None
        assert election_id in voting_service.elections

        election = voting_service.elections[election_id]
        assert election.message_id == valid_message.message_id
        assert election.strategy == VotingStrategy.QUORUM
        assert set(election.participants) == set(participants)
        assert election.status == "OPEN"

    async def test_cast_vote_success(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test successfully casting a vote."""
        participants = ["agent-1", "agent-2"]
        election_id = await voting_service.create_election(valid_message, participants)

        vote = Vote(agent_id="agent-1", decision="APPROVE")
        result = await voting_service.cast_vote(election_id, vote)

        assert result is True
        election = voting_service.elections[election_id]
        assert "agent-1" in election.votes

    async def test_cast_vote_non_participant(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test voting by non-participant is rejected."""
        participants = ["agent-1", "agent-2"]
        election_id = await voting_service.create_election(valid_message, participants)

        vote = Vote(agent_id="agent-3", decision="APPROVE")  # Not a participant
        result = await voting_service.cast_vote(election_id, vote)

        assert result is False

    async def test_cast_vote_invalid_election(self, voting_service: VotingService) -> None:
        """Test voting on non-existent election fails."""
        vote = Vote(agent_id="agent-1", decision="APPROVE")
        result = await voting_service.cast_vote("non-existent-id", vote)

        assert result is False

    async def test_get_result_non_existent_election(self, voting_service: VotingService) -> None:
        """Test getting result of non-existent election."""
        result = await voting_service.get_result("non-existent-id")
        assert result is None


# =============================================================================
# Quorum Strategy Tests
# =============================================================================


class TestQuorumStrategy:
    """Tests for quorum voting strategy."""

    async def test_quorum_approve_early_resolution(
        self, quorum_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test quorum is reached with majority approvals."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await quorum_voting_service.create_election(valid_message, participants)

        # 2 out of 3 approve (more than 50%)
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE")
        )
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE")
        )

        election = quorum_voting_service.elections[election_id]
        assert election.status == "CLOSED"

    async def test_quorum_deny_early_resolution(
        self, quorum_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test quorum denies with majority denials."""
        participants = ["agent-1", "agent-2", "agent-3", "agent-4"]
        election_id = await quorum_voting_service.create_election(valid_message, participants)

        # 2 out of 4 deny (50%, which should trigger denial)
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="DENY")
        )
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="DENY")
        )

        election = quorum_voting_service.elections[election_id]
        assert election.status == "CLOSED"


# =============================================================================
# Unanimous Strategy Tests
# =============================================================================


class TestUnanimousStrategy:
    """Tests for unanimous voting strategy."""

    async def test_unanimous_approve_all_agree(
        self, unanimous_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test unanimous approval when all agree."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await unanimous_voting_service.create_election(valid_message, participants)

        # All 3 approve
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE")
        )
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE")
        )
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-3", decision="APPROVE")
        )

        election = unanimous_voting_service.elections[election_id]
        assert election.status == "CLOSED"

    async def test_unanimous_deny_single_denial(
        self, unanimous_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test unanimous fails with single denial."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await unanimous_voting_service.create_election(valid_message, participants)

        # First two approve, third denies
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE")
        )
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE")
        )
        await unanimous_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-3", decision="DENY")
        )

        election = unanimous_voting_service.elections[election_id]
        # After a denial in unanimous, election should be closed
        assert election.status == "CLOSED"


# =============================================================================
# Super Majority Strategy Tests
# =============================================================================


class TestSuperMajorityStrategy:
    """Tests for super majority (2/3) voting strategy."""

    async def test_super_majority_approve(
        self, super_majority_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test super majority approval with 2/3 votes."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await super_majority_voting_service.create_election(
            valid_message, participants
        )

        # 2 out of 3 approve (2/3 = 66.67%)
        await super_majority_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE")
        )
        await super_majority_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE")
        )

        election = super_majority_voting_service.elections[election_id]
        assert election.status == "CLOSED"

    async def test_super_majority_deny(
        self, super_majority_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test super majority denial with >1/3 denials."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await super_majority_voting_service.create_election(
            valid_message, participants
        )

        # 2 out of 3 deny (more than 1/3)
        await super_majority_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="DENY")
        )
        await super_majority_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="DENY")
        )

        election = super_majority_voting_service.elections[election_id]
        assert election.status == "CLOSED"


# =============================================================================
# Election Result Tests
# =============================================================================


class TestElectionResults:
    """Tests for election result retrieval."""

    async def test_get_result_open_election(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test getting result of open election returns None."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await voting_service.create_election(
            valid_message,
            participants,
            timeout=3600,  # Long timeout
        )

        # Only one vote cast, election still open
        await voting_service.cast_vote(election_id, Vote(agent_id="agent-1", decision="APPROVE"))

        result = await voting_service.get_result(election_id)
        # Should be None since election is still open
        assert result is None

    async def test_get_result_closed_election_approve(
        self, quorum_voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test getting result of closed approved election."""
        participants = ["agent-1", "agent-2", "agent-3"]
        election_id = await quorum_voting_service.create_election(valid_message, participants)

        # Majority approves
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE")
        )
        await quorum_voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE")
        )

        result = await quorum_voting_service.get_result(election_id)
        assert result == "APPROVE"


# =============================================================================
# Integration Tests
# =============================================================================


class TestVotingServiceIntegration:
    """Integration tests for voting service."""

    async def test_full_voting_workflow(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test complete voting workflow."""
        participants = ["agent-1", "agent-2", "agent-3"]

        # Create election
        election_id = await voting_service.create_election(valid_message, participants)
        assert election_id is not None

        # Cast votes
        await voting_service.cast_vote(
            election_id, Vote(agent_id="agent-1", decision="APPROVE", reason="Looks good")
        )
        await voting_service.cast_vote(
            election_id, Vote(agent_id="agent-2", decision="APPROVE", reason="Constitutional")
        )

        # Election should be resolved
        election = voting_service.elections[election_id]
        assert election.status == "CLOSED"

        # Get result
        result = await voting_service.get_result(election_id)
        assert result == "APPROVE"

    async def test_multiple_concurrent_elections(
        self, voting_service: VotingService, valid_message: AgentMessage
    ) -> None:
        """Test running multiple elections concurrently."""
        # Create a second message
        message2 = AgentMessage(
            from_agent="sender-2",
            to_agent="receiver-2",
            content={"action": "test2"},
            constitutional_hash=CONSTITUTIONAL_HASH,
        )

        participants = ["agent-1", "agent-2", "agent-3"]

        # Create two elections
        election_id_1 = await voting_service.create_election(valid_message, participants)
        election_id_2 = await voting_service.create_election(message2, participants)

        # Vote on first election
        await voting_service.cast_vote(election_id_1, Vote(agent_id="agent-1", decision="APPROVE"))
        await voting_service.cast_vote(election_id_1, Vote(agent_id="agent-2", decision="APPROVE"))

        # Vote on second election (denial)
        await voting_service.cast_vote(election_id_2, Vote(agent_id="agent-1", decision="DENY"))
        await voting_service.cast_vote(election_id_2, Vote(agent_id="agent-2", decision="DENY"))

        # Check both elections are resolved correctly
        result_1 = await voting_service.get_result(election_id_1)
        result_2 = await voting_service.get_result(election_id_2)

        assert result_1 == "APPROVE"
        # Second election should have been closed due to denials
        assert voting_service.elections[election_id_2].status == "CLOSED"
