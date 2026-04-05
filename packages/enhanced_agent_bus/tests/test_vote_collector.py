"""
Tests for Event-Driven Vote Collector
Constitutional Hash: 608508a9bd224290

Validates:
- VoteEvent serialization/deserialization
- VoteSession consensus checking with weighted voting
- EventDrivenVoteCollector pub/sub integration
- Timeout handling
- Concurrent session support
"""

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Import test targets
from enhanced_agent_bus.deliberation_layer.vote_collector import (
    EventDrivenVoteCollector,
    VoteEvent,
    VoteSession,
    get_vote_collector,
    reset_vote_collector,
)


class TestVoteEvent:
    """Tests for VoteEvent dataclass."""

    def test_create_vote_event(self):
        """Test creating a vote event."""
        vote = VoteEvent(
            vote_id="vote-1",
            message_id="msg-1",
            agent_id="agent-1",
            decision="approve",
            reasoning="Policy compliant",
            confidence=0.95,
            weight=1.5,
        )

        assert vote.vote_id == "vote-1"
        assert vote.message_id == "msg-1"
        assert vote.agent_id == "agent-1"
        assert vote.decision == "approve"
        assert vote.confidence == 0.95
        assert vote.weight == 1.5

    def test_vote_event_to_dict(self):
        """Test serializing vote event to dictionary."""
        vote = VoteEvent(
            vote_id="vote-1",
            message_id="msg-1",
            agent_id="agent-1",
            decision="approve",
            reasoning="Test",
            confidence=1.0,
        )

        data = vote.to_dict()

        assert data["vote_id"] == "vote-1"
        assert data["message_id"] == "msg-1"
        assert data["decision"] == "approve"
        assert "timestamp" in data

    def test_vote_event_from_dict(self):
        """Test deserializing vote event from dictionary."""
        data = {
            "vote_id": "vote-2",
            "message_id": "msg-2",
            "agent_id": "agent-2",
            "decision": "reject",
            "reasoning": "Policy violation",
            "confidence": 0.8,
            "weight": 2.0,
            "timestamp": "2025-01-01T12:00:00+00:00",
        }

        vote = VoteEvent.from_dict(data)

        assert vote.vote_id == "vote-2"
        assert vote.decision == "reject"
        assert vote.weight == 2.0


class TestVoteSession:
    """Tests for VoteSession consensus logic."""

    def test_add_vote_to_session(self):
        """Test adding votes to a session."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )

        vote1 = VoteEvent(
            vote_id="v1",
            message_id="msg-1",
            agent_id="agent-1",
            decision="approve",
            reasoning="OK",
            confidence=1.0,
        )

        added = session.add_vote(vote1)
        assert added is True
        assert len(session.votes) == 1

    def test_prevent_duplicate_votes(self):
        """Test that duplicate votes from same agent are rejected."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )

        vote1 = VoteEvent(
            vote_id="v1",
            message_id="msg-1",
            agent_id="agent-1",
            decision="approve",
            reasoning="OK",
            confidence=1.0,
        )
        vote2 = VoteEvent(
            vote_id="v2",
            message_id="msg-1",
            agent_id="agent-1",  # Same agent
            decision="reject",
            reasoning="Changed mind",
            confidence=1.0,
        )

        session.add_vote(vote1)
        added = session.add_vote(vote2)

        assert added is False
        assert len(session.votes) == 1

    def test_check_consensus_insufficient_votes(self):
        """Test consensus check with insufficient votes."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )

        session.add_vote(
            VoteEvent(
                vote_id="v1",
                message_id="msg-1",
                agent_id="agent-1",
                decision="approve",
                reasoning="OK",
                confidence=1.0,
            )
        )

        result = session.check_consensus()

        assert result["consensus_reached"] is False
        assert result["reason"] == "insufficient_votes"
        assert result["votes_received"] == 1

    def test_check_consensus_approved(self):
        """Test consensus check with approval threshold met."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )

        # Add 3 votes: 2 approve, 1 reject = 66.7% approval
        for i, decision in enumerate(["approve", "approve", "reject"]):
            session.add_vote(
                VoteEvent(
                    vote_id=f"v{i}",
                    message_id="msg-1",
                    agent_id=f"agent-{i}",
                    decision=decision,
                    reasoning="Test",
                    confidence=1.0,
                )
            )

        result = session.check_consensus()

        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"
        assert result["approval_rate"] >= 0.66

    def test_check_consensus_rejected(self):
        """Test consensus check with rejection threshold met."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300,
        )

        # Add 3 votes: 2 reject, 1 approve
        for i, decision in enumerate(["reject", "reject", "approve"]):
            session.add_vote(
                VoteEvent(
                    vote_id=f"v{i}",
                    message_id="msg-1",
                    agent_id=f"agent-{i}",
                    decision=decision,
                    reasoning="Test",
                    confidence=1.0,
                )
            )

        result = session.check_consensus()

        assert result["consensus_reached"] is True
        assert result["decision"] == "rejected"

    def test_weighted_voting(self):
        """Test consensus with weighted votes."""
        session = VoteSession(
            session_id="session-1",
            message_id="msg-1",
            required_votes=2,
            consensus_threshold=0.66,
            timeout_seconds=300,
            agent_weights={"agent-1": 3.0, "agent-2": 1.0},  # Agent 1 has 3x weight
        )

        # Agent 1 approves (weight 3), Agent 2 rejects (weight 1)
        # Note: weights are stabilized via softmax in _stabilize_weights()
        # softmax([3.0, 1.0]) ≈ [0.88, 0.12], so approval_rate ≈ 0.88
        session.add_vote(
            VoteEvent(
                vote_id="v1",
                message_id="msg-1",
                agent_id="agent-1",
                decision="approve",
                reasoning="Test",
                confidence=1.0,
            )
        )
        session.add_vote(
            VoteEvent(
                vote_id="v2",
                message_id="msg-1",
                agent_id="agent-2",
                decision="reject",
                reasoning="Test",
                confidence=1.0,
            )
        )

        result = session.check_consensus()

        assert result["consensus_reached"] is True
        assert result["decision"] == "approved"
        # Approval rate depends on whether Rust/Torch stabilization is available:
        # - With softmax stabilization: ~0.88 (softmax([3.0, 1.0]))
        # - Without stabilization: 0.75 (3/(3+1) = 0.75)
        # Accept either value since stabilization is environment-dependent
        approval_rate = result["approval_rate"]
        assert approval_rate >= 0.66, f"Approval rate {approval_rate} below threshold"
        assert approval_rate <= 0.90, f"Approval rate {approval_rate} unexpectedly high"


class TestEventDrivenVoteCollector:
    """Tests for EventDrivenVoteCollector."""

    @pytest.fixture
    def collector(self):
        """Create a collector instance."""
        reset_vote_collector()
        return EventDrivenVoteCollector(redis_url="redis://localhost:6379")

    async def test_create_vote_session(self, collector):
        """Test creating a vote session."""
        session_id = await collector.create_vote_session(
            message_id="msg-test",
            required_votes=3,
            consensus_threshold=0.7,
            timeout_seconds=60,
        )

        assert session_id is not None
        assert "msg-test" in session_id
        assert collector.get_session_count() == 1

    async def test_submit_vote_in_memory(self, collector):
        """Test submitting a vote (in-memory fallback)."""
        # Create session first
        session_id = await collector.create_vote_session(
            message_id="msg-vote",
            required_votes=1,
            timeout_seconds=10,
        )

        # Submit vote
        result = await collector.submit_vote(
            message_id="msg-vote",
            agent_id="agent-1",
            decision="approve",
            reasoning="Test vote",
            confidence=0.9,
        )

        assert result is True

    async def test_get_session_info(self, collector):
        """Test retrieving session information."""
        session_id = await collector.create_vote_session(
            message_id="msg-info",
            required_votes=5,
            consensus_threshold=0.8,
            timeout_seconds=120,
        )

        info = await collector.get_session_info(session_id)

        assert info is not None
        assert info["message_id"] == "msg-info"
        assert info["required_votes"] == 5
        assert info["consensus_threshold"] == 0.8
        assert info["completed"] is False

    async def test_max_concurrent_sessions(self, collector):
        """Test concurrent session limit."""
        collector.max_concurrent_sessions = 5

        # Create max sessions
        for i in range(5):
            await collector.create_vote_session(
                message_id=f"msg-{i}",
                required_votes=3,
                timeout_seconds=300,
            )

        assert collector.get_session_count() == 5

        # Next session should fail
        with pytest.raises(RuntimeError, match="Maximum concurrent sessions"):
            await collector.create_vote_session(
                message_id="msg-overflow",
                required_votes=3,
                timeout_seconds=300,
            )

    async def test_vote_event_processing(self, collector):
        """Test processing vote events."""
        session_id = await collector.create_vote_session(
            message_id="msg-process",
            required_votes=2,
            timeout_seconds=10,
        )

        # Manually create and process vote events
        vote1 = VoteEvent(
            vote_id="v1",
            message_id="msg-process",
            agent_id="agent-1",
            decision="approve",
            reasoning="OK",
            confidence=1.0,
        )
        vote2 = VoteEvent(
            vote_id="v2",
            message_id="msg-process",
            agent_id="agent-2",
            decision="approve",
            reasoning="OK",
            confidence=1.0,
        )

        await collector._process_vote_event(vote1)
        await collector._process_vote_event(vote2)

        # Session should be completed with consensus
        info = await collector.get_session_info(session_id)
        assert info["votes_received"] == 2
        assert info["consensus"]["consensus_reached"] is True


class TestGlobalVoteCollector:
    """Tests for global vote collector singleton."""

    def test_get_vote_collector_singleton(self):
        """Test singleton behavior."""
        reset_vote_collector()

        collector1 = get_vote_collector()
        collector2 = get_vote_collector()

        assert collector1 is collector2

    def test_reset_vote_collector(self):
        """Test resetting singleton."""
        reset_vote_collector()

        collector1 = get_vote_collector()
        reset_vote_collector()
        collector2 = get_vote_collector()

        assert collector1 is not collector2
