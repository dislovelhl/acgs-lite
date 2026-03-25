"""
ACGS-2 Enhanced Agent Bus - Voting Service Helper Tests
Constitutional Hash: 608508a9bd224290

Unit tests for extracted helper functions in VotingService.
Tests each helper function independently with comprehensive edge cases.
"""

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

from enhanced_agent_bus.deliberation_layer.voting_service import (
    Vote,
    VotingService,
    VotingStrategy,
)
from enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage

# =============================================================================
# Test Data and Fixtures
# =============================================================================


@pytest.fixture
def sample_vote() -> Vote:
    """Create a sample vote for testing."""
    return Vote(
        agent_id="agent-1",  # Match the participant in sample_election_data
        decision="APPROVE",
        reason="Test approval",
        timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_election_data() -> dict:
    """Create sample election data for testing."""
    return {
        "election_id": "election-123",
        "message_id": "msg-456",
        "tenant_id": "test-tenant",
        "strategy": VotingStrategy.QUORUM.value,
        "participants": ["agent-1", "agent-2", "agent-3"],
        "participant_weights": {"agent-1": 1.0, "agent-2": 1.5, "agent-3": 2.0},
        "votes": {
            "agent-1": {
                "agent_id": "agent-1",
                "decision": "APPROVE",
                "reason": "Looks good",
                "timestamp": "2024-01-01T12:00:00+00:00",
            },
            "agent-2": {
                "agent_id": "agent-2",
                "decision": "DENY",
                "reason": "Policy violation",
                "timestamp": "2024-01-01T12:01:00+00:00",
            },
        },
        "status": "OPEN",
        "created_at": datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
        "expires_at": datetime(2024, 1, 1, 13, 0, 0, tzinfo=UTC),
    }


@pytest.fixture
def voting_service() -> VotingService:
    """Create a voting service instance for testing helpers."""
    return VotingService(force_in_memory=True)


# =============================================================================
# Tests for _validate_vote_eligibility helper
# =============================================================================


class TestValidateVoteEligibility:
    """Tests for _validate_vote_eligibility helper function."""

    async def test_validate_vote_eligibility_success(
        self, voting_service: VotingService, sample_vote: Vote, sample_election_data: dict
    ) -> None:
        """Test successful vote eligibility validation."""
        # Setup election in memory
        election_id = "election-123"
        voting_service._in_memory_elections = {election_id: sample_election_data}

        # Test validation
        result = await voting_service._validate_vote_eligibility(election_id, sample_vote)

        assert result is not None
        assert result == sample_election_data

    async def test_validate_vote_eligibility_election_not_found(
        self, voting_service: VotingService, sample_vote: Vote
    ) -> None:
        """Test validation fails when election not found."""
        result = await voting_service._validate_vote_eligibility("nonexistent", sample_vote)
        assert result is None

    async def test_validate_vote_eligibility_election_closed(
        self, voting_service: VotingService, sample_vote: Vote, sample_election_data: dict
    ) -> None:
        """Test validation fails when election is closed."""
        election_id = "election-123"
        sample_election_data["status"] = "CLOSED"
        voting_service._in_memory_elections = {election_id: sample_election_data}

        result = await voting_service._validate_vote_eligibility(election_id, sample_vote)
        assert result is None

    async def test_validate_vote_eligibility_not_participant(
        self, voting_service: VotingService, sample_election_data: dict
    ) -> None:
        """Test validation fails when agent is not a participant."""
        election_id = "election-123"
        voting_service._in_memory_elections = {election_id: sample_election_data}

        non_participant_vote = Vote(agent_id="not-a-participant", decision="APPROVE")
        result = await voting_service._validate_vote_eligibility(election_id, non_participant_vote)
        assert result is None

    async def test_validate_vote_eligibility_election_expired(
        self, voting_service: VotingService, sample_vote: Vote, sample_election_data: dict
    ) -> None:
        """Test validation fails when election is expired."""
        election_id = "election-123"
        sample_election_data["status"] = "EXPIRED"
        voting_service._in_memory_elections = {election_id: sample_election_data}

        result = await voting_service._validate_vote_eligibility(election_id, sample_vote)
        assert result is None


# =============================================================================
# Tests for _prepare_vote_dict helper
# =============================================================================


class TestPrepareVoteDict:
    """Tests for _prepare_vote_dict static helper function."""

    def test_prepare_vote_dict_with_datetime(self, sample_vote: Vote) -> None:
        """Test preparing vote dict with datetime timestamp."""
        result = VotingService._prepare_vote_dict(sample_vote)

        expected = {
            "agent_id": "agent-1",
            "decision": "APPROVE",
            "reason": "Test approval",
            "timestamp": "2024-01-01T12:00:00+00:00",
        }

        assert result == expected

    def test_prepare_vote_dict_with_string_timestamp(self) -> None:
        """Test preparing vote dict with string timestamp."""
        vote = Vote(
            agent_id="agent-1",
            decision="DENY",
            reason="Policy issue",
            timestamp="2024-01-01T12:00:00+00:00",  # Already a string
        )

        result = VotingService._prepare_vote_dict(vote)

        expected = {
            "agent_id": "agent-1",
            "decision": "DENY",
            "reason": "Policy issue",
            "timestamp": "2024-01-01T12:00:00+00:00",
        }

        assert result == expected

    def test_prepare_vote_dict_no_reason(self) -> None:
        """Test preparing vote dict with no reason."""
        vote = Vote(
            agent_id="agent-1",
            decision="ABSTAIN",
            reason=None,
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        )

        result = VotingService._prepare_vote_dict(vote)

        expected = {
            "agent_id": "agent-1",
            "decision": "ABSTAIN",
            "reason": None,
            "timestamp": "2024-01-01T12:00:00+00:00",
        }

        assert result == expected


# =============================================================================
# Tests for _store_vote_in_memory helper
# =============================================================================


class TestStoreVoteInMemory:
    """Tests for _store_vote_in_memory helper function."""

    def test_store_vote_in_memory_success(self, voting_service: VotingService) -> None:
        """Test successful in-memory vote storage."""
        election_id = "election-123"
        election_data = {"votes": {}}
        voting_service._in_memory_elections = {election_id: election_data}

        vote_dict = {
            "agent_id": "agent-1",
            "decision": "APPROVE",
            "reason": "Test vote",
            "timestamp": "2024-01-01T12:00:00+00:00",
        }

        voting_service._store_vote_in_memory(election_id, vote_dict)

        assert "agent-1" in voting_service._in_memory_elections[election_id]["votes"]
        assert voting_service._in_memory_elections[election_id]["votes"]["agent-1"] == vote_dict

    def test_store_vote_in_memory_election_not_exist(self, voting_service: VotingService) -> None:
        """Test storing vote when election doesn't exist (should not crash)."""
        election_id = "nonexistent"
        vote_dict = {"agent_id": "agent-1", "decision": "APPROVE"}

        # Should not raise an exception
        voting_service._store_vote_in_memory(election_id, vote_dict)

    def test_store_vote_in_memory_no_votes_key(self, voting_service: VotingService) -> None:
        """Test storing vote creates votes key if missing."""
        election_id = "election-123"
        election_data = {}  # No votes key
        voting_service._in_memory_elections = {election_id: election_data}

        vote_dict = {"agent_id": "agent-1", "decision": "APPROVE"}

        voting_service._store_vote_in_memory(election_id, vote_dict)

        assert "votes" in voting_service._in_memory_elections[election_id]
        assert voting_service._in_memory_elections[election_id]["votes"]["agent-1"] == vote_dict

    def test_store_vote_in_memory_no_in_memory_elections(self) -> None:
        """Test storing vote when _in_memory_elections doesn't exist."""
        voting_service = VotingService(force_in_memory=True)
        # Don't initialize _in_memory_elections
        delattr(voting_service, "_in_memory_elections")

        vote_dict = {"agent_id": "agent-1", "decision": "APPROVE"}

        # Should not raise an exception
        voting_service._store_vote_in_memory("election-123", vote_dict)


# =============================================================================
# Tests for _get_voting_strategy helper
# =============================================================================


class TestGetVotingStrategy:
    """Tests for _get_voting_strategy helper function."""

    def test_get_voting_strategy_quorum(self, voting_service: VotingService) -> None:
        """Test getting quorum strategy from election data."""
        election_data = {"strategy": "quorum"}

        result = voting_service._get_voting_strategy(election_data)

        assert result == VotingStrategy.QUORUM

    def test_get_voting_strategy_unanimous(self, voting_service: VotingService) -> None:
        """Test getting unanimous strategy from election data."""
        election_data = {"strategy": "unanimous"}

        result = voting_service._get_voting_strategy(election_data)

        assert result == VotingStrategy.UNANIMOUS

    def test_get_voting_strategy_super_majority(self, voting_service: VotingService) -> None:
        """Test getting super-majority strategy from election data."""
        election_data = {"strategy": "super-majority"}

        result = voting_service._get_voting_strategy(election_data)

        assert result == VotingStrategy.SUPER_MAJORITY

    def test_get_voting_strategy_invalid_fallback(self, voting_service: VotingService) -> None:
        """Test fallback to default strategy for invalid strategy."""
        election_data = {"strategy": "invalid-strategy"}

        result = voting_service._get_voting_strategy(election_data)

        assert result == voting_service.default_strategy

    def test_get_voting_strategy_missing_key(self, voting_service: VotingService) -> None:
        """Test fallback to default strategy when strategy key missing."""
        election_data = {}

        result = voting_service._get_voting_strategy(election_data)

        assert result == voting_service.default_strategy


# =============================================================================
# Tests for _calculate_vote_weights helper
# =============================================================================


class TestCalculateVoteWeights:
    """Tests for _calculate_vote_weights helper function."""

    def test_calculate_vote_weights_basic(
        self, voting_service: VotingService, sample_election_data: dict
    ) -> None:
        """Test basic vote weight calculation."""
        approvals, denials, total = voting_service._calculate_vote_weights(sample_election_data)

        # agent-1 (weight 1.0) voted APPROVE, agent-2 (weight 1.5) voted DENY
        assert approvals == 1.0  # agent-1's approval
        assert denials == 1.5  # agent-2's denial
        assert total == 4.5  # sum of all participant weights (1.0 + 1.5 + 2.0)

    def test_calculate_vote_weights_no_votes(self, voting_service: VotingService) -> None:
        """Test weight calculation with no votes cast."""
        election_data = {
            "participants": ["agent-1", "agent-2"],
            "participant_weights": {"agent-1": 1.0, "agent-2": 2.0},
            "votes": {},
        }

        approvals, denials, total = voting_service._calculate_vote_weights(election_data)

        assert approvals == 0.0
        assert denials == 0.0
        assert total == 3.0  # 1.0 + 2.0

    def test_calculate_vote_weights_default_weights(self, voting_service: VotingService) -> None:
        """Test weight calculation when participant_weights missing (defaults to 1.0)."""
        election_data = {
            "participants": ["agent-1", "agent-2", "agent-3"],
            "votes": {
                "agent-1": {"agent_id": "agent-1", "decision": "APPROVE"},
                "agent-2": {"agent_id": "agent-2", "decision": "DENY"},
            },
        }

        approvals, denials, total = voting_service._calculate_vote_weights(election_data)

        assert approvals == 1.0  # agent-1 with default weight 1.0
        assert denials == 1.0  # agent-2 with default weight 1.0
        assert total == 3.0  # all 3 participants with default weight 1.0

    def test_calculate_vote_weights_abstain_ignored(self, voting_service: VotingService) -> None:
        """Test that abstain votes are ignored in weight calculation."""
        election_data = {
            "participants": ["agent-1", "agent-2", "agent-3"],
            "participant_weights": {"agent-1": 1.0, "agent-2": 1.0, "agent-3": 1.0},
            "votes": {
                "agent-1": {"agent_id": "agent-1", "decision": "APPROVE"},
                "agent-2": {"agent_id": "agent-2", "decision": "ABSTAIN"},
                "agent-3": {"agent_id": "agent-3", "decision": "DENY"},
            },
        }

        approvals, denials, total = voting_service._calculate_vote_weights(election_data)

        assert approvals == 1.0  # Only agent-1's approval
        assert denials == 1.0  # Only agent-3's denial
        assert total == 3.0  # All participants count toward total

    def test_calculate_vote_weights_missing_participants(
        self, voting_service: VotingService
    ) -> None:
        """Test weight calculation when participants key missing."""
        election_data = {
            "participant_weights": {"agent-1": 2.0},
            "votes": {"agent-1": {"agent_id": "agent-1", "decision": "APPROVE"}},
        }

        approvals, denials, total = voting_service._calculate_vote_weights(election_data)

        assert approvals == 2.0  # agent-1's weighted approval
        assert denials == 0.0
        assert total == 0.0  # No participants to sum


# =============================================================================
# Tests for _evaluate_strategy_resolution helper
# =============================================================================


class TestEvaluateStrategyResolution:
    """Tests for _evaluate_strategy_resolution static helper function."""

    def test_evaluate_strategy_resolution_quorum(self) -> None:
        """Test strategy resolution evaluation for quorum."""
        weight_info = (3.0, 1.0, 5.0)  # approvals=3, denials=1, total=5

        resolved, decision = VotingService._evaluate_strategy_resolution(
            VotingStrategy.QUORUM, weight_info
        )

        assert resolved is True
        assert decision == "APPROVE"  # 3 > 5/2 (2.5)

    def test_evaluate_strategy_resolution_unanimous(self) -> None:
        """Test strategy resolution evaluation for unanimous."""
        weight_info = (5.0, 0.0, 5.0)  # all approve, no denials

        resolved, decision = VotingService._evaluate_strategy_resolution(
            VotingStrategy.UNANIMOUS, weight_info
        )

        assert resolved is True
        assert decision == "APPROVE"

    def test_evaluate_strategy_resolution_super_majority(self) -> None:
        """Test strategy resolution evaluation for super majority."""
        weight_info = (4.0, 1.0, 6.0)  # approvals=4, denials=1, total=6

        resolved, decision = VotingService._evaluate_strategy_resolution(
            VotingStrategy.SUPER_MAJORITY, weight_info
        )

        assert resolved is True
        assert decision == "APPROVE"  # 4 >= 6*2/3 (4.0)

    def test_evaluate_strategy_resolution_no_resolution(self) -> None:
        """Test strategy resolution when no resolution reached."""
        weight_info = (1.0, 1.0, 5.0)  # insufficient votes

        resolved, decision = VotingService._evaluate_strategy_resolution(
            VotingStrategy.QUORUM, weight_info
        )

        assert resolved is False
        assert decision == "DENY"


# =============================================================================
# Tests for _check_quorum_resolution helper
# =============================================================================


class TestCheckQuorumResolution:
    """Tests for _check_quorum_resolution static helper function."""

    def test_check_quorum_resolution_approve_simple_majority(self) -> None:
        """Test quorum approval with simple majority."""
        resolved, decision = VotingService._check_quorum_resolution(3.0, 1.0, 5.0)

        assert resolved is True
        assert decision == "APPROVE"  # 3 > 5/2 (2.5)

    def test_check_quorum_resolution_approve_exactly_half_plus_one(self) -> None:
        """Test quorum approval with exactly half plus one."""
        resolved, decision = VotingService._check_quorum_resolution(2.1, 1.9, 4.0)

        assert resolved is True
        assert decision == "APPROVE"  # 2.1 > 4/2 (2.0)

    def test_check_quorum_resolution_deny_half_or_more(self) -> None:
        """Test quorum denial with half or more denials."""
        resolved, decision = VotingService._check_quorum_resolution(2.0, 2.0, 4.0)

        assert resolved is True
        assert decision == "DENY"  # 2.0 >= 4/2 (2.0)

    def test_check_quorum_resolution_deny_more_than_half(self) -> None:
        """Test quorum denial with more than half denials."""
        resolved, decision = VotingService._check_quorum_resolution(1.0, 3.0, 4.0)

        assert resolved is True
        assert decision == "DENY"  # 3.0 >= 4/2 (2.0)

    def test_check_quorum_resolution_no_resolution(self) -> None:
        """Test no resolution when insufficient votes."""
        resolved, decision = VotingService._check_quorum_resolution(2.0, 1.0, 5.0)

        assert resolved is False
        assert decision == "DENY"  # 2 <= 5/2 (2.5) and 1 < 5/2 (2.5)

    def test_check_quorum_resolution_edge_case_tie(self) -> None:
        """Test edge case with exact tie."""
        resolved, decision = VotingService._check_quorum_resolution(2.0, 2.0, 4.0)

        assert resolved is True
        assert decision == "DENY"  # tie goes to denial


# =============================================================================
# Tests for _check_unanimous_resolution helper
# =============================================================================


class TestCheckUnanimousResolution:
    """Tests for _check_unanimous_resolution static helper function."""

    def test_check_unanimous_resolution_approve_all(self) -> None:
        """Test unanimous approval when all participants approve."""
        resolved, decision = VotingService._check_unanimous_resolution(5.0, 0.0, 5.0)

        assert resolved is True
        assert decision == "APPROVE"  # approvals >= total

    def test_check_unanimous_resolution_deny_single_denial(self) -> None:
        """Test unanimous failure with single denial."""
        resolved, decision = VotingService._check_unanimous_resolution(4.0, 1.0, 5.0)

        assert resolved is True
        assert decision == "DENY"  # denials > 0

    def test_check_unanimous_resolution_no_resolution_partial_votes(self) -> None:
        """Test no resolution when votes incomplete."""
        resolved, decision = VotingService._check_unanimous_resolution(3.0, 0.0, 5.0)

        assert resolved is False
        assert decision == "DENY"  # approvals < total and denials == 0

    def test_check_unanimous_resolution_zero_total_edge_case(self) -> None:
        """Test edge case with zero total weight."""
        resolved, decision = VotingService._check_unanimous_resolution(0.0, 0.0, 0.0)

        assert resolved is True
        assert decision == "APPROVE"  # 0 >= 0


# =============================================================================
# Tests for _check_super_majority_resolution helper
# =============================================================================


class TestCheckSuperMajorityResolution:
    """Tests for _check_super_majority_resolution static helper function."""

    def test_check_super_majority_resolution_approve_two_thirds(self) -> None:
        """Test super majority approval with exactly 2/3."""
        resolved, decision = VotingService._check_super_majority_resolution(4.0, 2.0, 6.0)

        assert resolved is True
        assert decision == "APPROVE"  # 4 >= 6*2/3 (4.0)

    def test_check_super_majority_resolution_approve_more_than_two_thirds(self) -> None:
        """Test super majority approval with more than 2/3."""
        resolved, decision = VotingService._check_super_majority_resolution(5.0, 1.0, 6.0)

        assert resolved is True
        assert decision == "APPROVE"  # 5 >= 6*2/3 (4.0)

    def test_check_super_majority_resolution_deny_more_than_one_third(self) -> None:
        """Test super majority denial with more than 1/3 denials."""
        resolved, decision = VotingService._check_super_majority_resolution(2.0, 2.5, 6.0)

        assert resolved is True
        assert decision == "DENY"  # 2.5 > 6/3 (2.0)

    def test_check_super_majority_resolution_deny_exactly_one_third_plus(self) -> None:
        """Test super majority denial with exactly 1/3 + epsilon denials."""
        resolved, decision = VotingService._check_super_majority_resolution(2.0, 2.1, 6.0)

        assert resolved is True
        assert decision == "DENY"  # 2.1 > 6/3 (2.0)

    def test_check_super_majority_resolution_no_resolution(self) -> None:
        """Test no resolution when insufficient votes."""
        resolved, decision = VotingService._check_super_majority_resolution(3.0, 2.0, 6.0)

        assert resolved is False
        assert decision == "DENY"  # 3 < 6*2/3 (4.0) and 2 <= 6/3 (2.0)

    def test_check_super_majority_resolution_edge_case_exactly_one_third(self) -> None:
        """Test edge case with exactly 1/3 denials."""
        resolved, decision = VotingService._check_super_majority_resolution(2.0, 2.0, 6.0)

        assert resolved is False
        assert decision == "DENY"  # 2 <= 6/3 (2.0), so not resolved yet


# =============================================================================
# Integration Tests for Helper Functions
# =============================================================================


class TestHelpersIntegration:
    """Integration tests showing helpers working together."""

    async def test_helpers_workflow(
        self, voting_service: VotingService, sample_election_data: dict
    ) -> None:
        """Test helpers working together in typical workflow."""
        election_id = "election-123"
        voting_service._in_memory_elections = {election_id: sample_election_data}

        # Create a new vote
        new_vote = Vote(agent_id="agent-3", decision="APPROVE", reason="Final approval")

        # 1. Validate eligibility
        election_data = await voting_service._validate_vote_eligibility(election_id, new_vote)
        assert election_data is not None

        # 2. Prepare vote dict
        vote_dict = voting_service._prepare_vote_dict(new_vote)
        assert vote_dict["agent_id"] == "agent-3"

        # 3. Store in memory
        voting_service._store_vote_in_memory(election_id, vote_dict)
        assert "agent-3" in voting_service._in_memory_elections[election_id]["votes"]

        # 4. Get strategy and calculate weights
        strategy = voting_service._get_voting_strategy(election_data)
        assert strategy == VotingStrategy.QUORUM

        # Update election data with new vote for weight calculation
        updated_election_data = voting_service._in_memory_elections[election_id]
        weight_info = voting_service._calculate_vote_weights(updated_election_data)

        # agent-1 (1.0) + agent-3 (2.0) = 3.0 approvals
        # agent-2 (1.5) = 1.5 denials
        # total = 4.5
        approvals, denials, total = weight_info
        assert approvals == 3.0  # 1.0 + 2.0
        assert denials == 1.5
        assert total == 4.5

        # 5. Check resolution
        resolved, decision = voting_service._evaluate_strategy_resolution(strategy, weight_info)
        assert resolved is True
        assert decision == "APPROVE"  # 3.0 > 4.5/2 (2.25)

    def test_static_helpers_independence(self) -> None:
        """Test that static helpers work independently of instance state."""
        # Test _prepare_vote_dict
        vote = Vote(agent_id="test", decision="APPROVE")
        vote_dict = VotingService._prepare_vote_dict(vote)
        assert vote_dict["agent_id"] == "test"

        # Test resolution helpers
        assert VotingService._check_quorum_resolution(3, 1, 4) == (True, "APPROVE")
        assert VotingService._check_unanimous_resolution(4, 0, 4) == (True, "APPROVE")
        assert VotingService._check_super_majority_resolution(3, 1, 4) == (True, "APPROVE")

        # Test _evaluate_strategy_resolution
        resolved, decision = VotingService._evaluate_strategy_resolution(
            VotingStrategy.QUORUM, (3, 1, 4)
        )
        assert resolved is True
        assert decision == "APPROVE"
