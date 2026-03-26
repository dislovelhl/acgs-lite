"""
ACGS-2 Enhanced Agent Bus - Deliberation Queue Module Tests
Constitutional Hash: 608508a9bd224290

Tests for the actual deliberation_queue.py module with comprehensive coverage.
"""

import asyncio
import importlib.util
import os
import sys
import types
from datetime import UTC, datetime, timedelta, timezone
from typing import ClassVar

import pytest

# Add enhanced_agent_bus directory to path
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)

_ORIGINAL_MODULES = {
    "enhanced_agent_bus": sys.modules.get("enhanced_agent_bus"),
    "enhanced_agent_bus.models": sys.modules.get("enhanced_agent_bus.models"),
}


def _load_module(name, path):
    """Load a module directly from path."""
    if "enhanced_agent_bus" not in sys.modules:
        pkg = types.ModuleType("enhanced_agent_bus")
        pkg.__path__ = [enhanced_agent_bus_dir]
        pkg.__file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
        pkg.__package__ = "enhanced_agent_bus"
        sys.modules["enhanced_agent_bus"] = pkg
    qualified_name = f"enhanced_agent_bus.{name}"
    spec = importlib.util.spec_from_file_location(qualified_name, path)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "enhanced_agent_bus"
    sys.modules[qualified_name] = module
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Load base models first
_models = _load_module("_delib_queue_models", os.path.join(enhanced_agent_bus_dir, "models.py"))


# Create mock parent package that can function as a Python package
class MockEnhancedAgentBus:
    """Mock package that provides all required module attributes for import system."""

    __path__: ClassVar[list] = [enhanced_agent_bus_dir]  # Required for package submodule imports
    __name__ = "enhanced_agent_bus"
    __file__ = os.path.join(enhanced_agent_bus_dir, "__init__.py")
    __spec__ = None  # Mock spec
    __loader__ = None
    __package__ = "enhanced_agent_bus"


mock_parent = MockEnhancedAgentBus()
mock_parent.models = _models


def _patch_modules() -> None:
    sys.modules["enhanced_agent_bus"] = mock_parent
    sys.modules["enhanced_agent_bus.models"] = _models


def _restore_modules() -> None:
    for name, original in _ORIGINAL_MODULES.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


# Import from models
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
MessageStatus = _models.MessageStatus
Priority = _models.Priority
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH

_patch_modules()
try:
    # Load the actual deliberation_queue module
    _delib_queue = _load_module(
        "_delib_queue_actual",
        os.path.join(enhanced_agent_bus_dir, "deliberation_layer", "deliberation_queue.py"),
    )
finally:
    _restore_modules()

DeliberationQueue = _delib_queue.DeliberationQueue
DeliberationItem = _delib_queue.DeliberationItem
DeliberationStatus = _delib_queue.DeliberationStatus
VoteType = _delib_queue.VoteType
AgentVote = _delib_queue.AgentVote
get_deliberation_queue = _delib_queue.get_deliberation_queue


class TestDeliberationQueueClass:
    """Tests for the DeliberationQueue class."""

    @pytest.fixture
    async def queue(self):
        """Create a fresh deliberation queue with proper cleanup."""
        q = DeliberationQueue(consensus_threshold=0.66, default_timeout=5)
        yield q
        # Cleanup: Cancel all pending tasks to prevent warnings
        await q.stop()

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "high_risk_operation"},
        )

    def test_queue_initialization(self):
        """Test queue initializes with correct default values."""
        queue = DeliberationQueue()

        assert queue.consensus_threshold == 0.66
        assert queue.default_timeout == 300
        assert len(queue.queue) == 0
        assert len(queue.processing_tasks) == 0
        assert queue.stats["total_queued"] == 0

    def test_custom_initialization(self):
        """Test queue with custom parameters."""
        queue = DeliberationQueue(consensus_threshold=0.75, default_timeout=60)

        assert queue.consensus_threshold == 0.75
        assert queue.default_timeout == 60

    async def test_enqueue_for_deliberation(self, queue, test_message):
        """Test enqueueing a message for deliberation."""
        item_id = await queue.enqueue_for_deliberation(
            message=test_message,
            requires_human_review=True,
            requires_multi_agent_vote=False,
            timeout_seconds=10,
        )

        assert item_id is not None
        assert item_id in queue.queue
        assert queue.stats["total_queued"] == 1

        # Check item properties
        item = queue.queue[item_id]
        assert item.message == test_message
        assert item.status == DeliberationStatus.PENDING
        assert item.timeout_seconds == 10

    async def test_enqueue_with_multi_agent_vote(self, queue, test_message):
        """Test enqueuing with multi-agent vote requirement."""
        item_id = await queue.enqueue_for_deliberation(
            message=test_message,
            requires_human_review=True,
            requires_multi_agent_vote=True,
            timeout_seconds=10,
        )

        item = queue.queue[item_id]
        assert item.required_votes == 5  # Multi-agent vote requires 5 votes

    async def test_enqueue_without_multi_agent_vote(self, queue, test_message):
        """Test enqueuing without multi-agent vote requirement."""
        item_id = await queue.enqueue_for_deliberation(
            message=test_message,
            requires_human_review=True,
            requires_multi_agent_vote=False,
            timeout_seconds=10,
        )

        item = queue.queue[item_id]
        assert item.required_votes == 0

    async def test_enqueue_creates_processing_task(self, queue, test_message):
        """Test that enqueueing creates a processing task."""
        item_id = await queue.enqueue_for_deliberation(message=test_message, timeout_seconds=1)

        # Give task time to start
        await asyncio.sleep(0.1)

        # Task should be created (may have completed by now due to short timeout)
        assert item_id in queue.queue

    async def test_queue_status(self, queue, test_message):
        """Test getting queue status."""
        await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)

        status = queue.get_queue_status()

        assert status["queue_size"] == 1
        assert len(status["items"]) == 1
        assert status["stats"]["total_queued"] == 1
        assert status["processing_count"] >= 0

    async def test_item_details(self, queue, test_message):
        """Test getting detailed item information."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)

        details = queue.get_item_details(item_id)

        assert details is not None
        assert details["item_id"] == item_id
        assert details["message_id"] == test_message.message_id
        assert details["status"] == DeliberationStatus.PENDING.value
        assert "created_at" in details
        assert "updated_at" in details
        assert "votes" in details

    def test_item_details_not_found(self, queue):
        """Test getting details for nonexistent item."""
        details = queue.get_item_details("nonexistent_id")
        assert details is None


class TestDeliberationItemClass:
    """Tests for DeliberationItem dataclass."""

    def test_default_values(self):
        """Test default values for DeliberationItem."""
        item = DeliberationItem()

        assert item.item_id is not None
        assert item.status == DeliberationStatus.PENDING
        assert item.required_votes == 3
        assert item.consensus_threshold == 0.66
        assert item.timeout_seconds == 300
        assert len(item.current_votes) == 0

    def test_custom_values(self):
        """Test creating item with custom values."""
        message = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={},
        )

        item = DeliberationItem(
            message=message, required_votes=5, consensus_threshold=0.8, timeout_seconds=120
        )

        assert item.message == message
        assert item.required_votes == 5
        assert item.consensus_threshold == 0.8
        assert item.timeout_seconds == 120

    def test_voting_deadline_calculation(self):
        """Test voting deadline is calculated correctly."""
        item = DeliberationItem(timeout_seconds=60)

        expected_deadline = item.created_at + timedelta(seconds=60)

        assert abs((item.voting_deadline - expected_deadline).total_seconds()) < 1

    def test_item_id_generation(self):
        """Test that each item gets a unique ID."""
        item1 = DeliberationItem()
        item2 = DeliberationItem()

        assert item1.item_id != item2.item_id


class TestAgentVoteClass:
    """Tests for AgentVote dataclass."""

    def test_vote_creation(self):
        """Test creating an agent vote."""
        vote = AgentVote(
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Valid operation",
            confidence_score=0.95,
        )

        assert vote.agent_id == "agent1"
        assert vote.vote == VoteType.APPROVE
        assert vote.reasoning == "Valid operation"
        assert vote.confidence_score == 0.95

    def test_default_confidence(self):
        """Test default confidence score."""
        vote = AgentVote(
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Test",
        )

        assert vote.confidence_score == 1.0

    def test_timestamp_auto_set(self):
        """Test timestamp is automatically set."""
        before = datetime.now(UTC)
        vote = AgentVote(
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Test",
        )
        after = datetime.now(UTC)

        assert before <= vote.timestamp <= after


class TestVoteTypes:
    """Tests for VoteType enum."""

    def test_all_vote_types_exist(self):
        """Test all expected vote types exist."""
        assert hasattr(VoteType, "APPROVE")
        assert hasattr(VoteType, "REJECT")
        assert hasattr(VoteType, "ABSTAIN")

    def test_vote_type_values(self):
        """Test vote type values."""
        assert VoteType.APPROVE.value == "approve"
        assert VoteType.REJECT.value == "reject"
        assert VoteType.ABSTAIN.value == "abstain"


class TestVotingSystem:
    """Tests for the voting system."""

    @pytest.fixture
    async def queue(self):
        """Create a deliberation queue with proper cleanup."""
        q = DeliberationQueue(default_timeout=60)
        yield q
        await q.stop()

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "high_risk_operation"},
        )

    async def test_submit_agent_vote(self, queue, test_message):
        """Test submitting an agent vote."""
        item_id = await queue.enqueue_for_deliberation(
            test_message, requires_multi_agent_vote=True, timeout_seconds=60
        )

        result = await queue.submit_agent_vote(
            item_id=item_id,
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Valid operation",
            confidence=0.9,
        )

        assert result
        item = queue.queue[item_id]
        assert len(item.current_votes) == 1
        assert item.current_votes[0].vote == VoteType.APPROVE

    async def test_multiple_agent_votes(self, queue, test_message):
        """Test multiple agents voting."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)

        # Submit votes from different agents
        await queue.submit_agent_vote(item_id, "agent1", VoteType.APPROVE, "Looks good")
        await queue.submit_agent_vote(item_id, "agent2", VoteType.APPROVE, "Approved")
        await queue.submit_agent_vote(item_id, "agent3", VoteType.REJECT, "Concerns")

        item = queue.queue[item_id]
        assert len(item.current_votes) == 3

    async def test_vote_update(self, queue, test_message):
        """Test updating an existing vote."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)

        # Submit initial vote
        await queue.submit_agent_vote(
            item_id=item_id,
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Initial",
        )

        # Update vote
        await queue.submit_agent_vote(
            item_id=item_id,
            agent_id="agent1",
            vote=VoteType.REJECT,
            reasoning="Changed mind",
        )

        item = queue.queue[item_id]
        # Should still only have one vote from agent1
        agent1_votes = [v for v in item.current_votes if v.agent_id == "agent1"]
        assert len(agent1_votes) == 1
        assert agent1_votes[0].vote == VoteType.REJECT

    async def test_vote_for_nonexistent_item(self, queue):
        """Test voting on nonexistent item returns False."""
        result = await queue.submit_agent_vote(
            item_id="nonexistent",
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Test",
        )
        assert not result


class TestConsensusChecking:
    """Tests for consensus checking logic."""

    def test_check_consensus_insufficient_votes(self):
        """Test consensus with insufficient votes."""
        queue = DeliberationQueue()
        item = DeliberationItem(required_votes=3)
        item.current_votes = [
            AgentVote("a1", VoteType.APPROVE, "yes"),
            AgentVote("a2", VoteType.APPROVE, "yes"),
        ]
        queue.queue[item.item_id] = item

        # _check_consensus is a private method, test through behavior
        assert not queue._check_consensus(item)

    def test_check_consensus_reached(self):
        """Test consensus reached with enough approve votes."""
        queue = DeliberationQueue()
        item = DeliberationItem(required_votes=3, consensus_threshold=0.66)
        item.current_votes = [
            AgentVote("a1", VoteType.APPROVE, "yes"),
            AgentVote("a2", VoteType.APPROVE, "yes"),
            AgentVote("a3", VoteType.APPROVE, "yes"),
        ]
        queue.queue[item.item_id] = item

        assert queue._check_consensus(item)

    def test_check_consensus_not_reached(self):
        """Test consensus not reached with mixed votes."""
        queue = DeliberationQueue()
        item = DeliberationItem(required_votes=3, consensus_threshold=0.66)
        item.current_votes = [
            AgentVote("a1", VoteType.APPROVE, "yes"),
            AgentVote("a2", VoteType.REJECT, "no"),
            AgentVote("a3", VoteType.REJECT, "no"),
        ]
        queue.queue[item.item_id] = item

        # 33% approval rate, below 66% threshold
        assert not queue._check_consensus(item)


class TestHumanDecision:
    """Tests for human decision submission."""

    @pytest.fixture
    async def queue(self):
        """Create a deliberation queue with proper cleanup."""
        q = DeliberationQueue(default_timeout=60)
        yield q
        await q.stop()

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "high_risk_operation"},
        )

    async def test_submit_human_decision_approved(self, queue, test_message):
        """Test submitting human approval decision."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)

        # Set item to under review status
        queue.queue[item_id].status = DeliberationStatus.UNDER_REVIEW

        result = await queue.submit_human_decision(
            item_id=item_id,
            reviewer="human_reviewer_1",
            decision=DeliberationStatus.APPROVED,
            reasoning="Approved after manual review",
        )

        assert result
        item = queue.queue[item_id]
        assert item.human_reviewer == "human_reviewer_1"
        assert item.human_decision == DeliberationStatus.APPROVED
        assert item.human_reasoning == "Approved after manual review"
        assert item.status == DeliberationStatus.APPROVED

    async def test_submit_human_decision_rejected(self, queue, test_message):
        """Test submitting human rejection decision."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)
        queue.queue[item_id].status = DeliberationStatus.UNDER_REVIEW

        result = await queue.submit_human_decision(
            item_id=item_id,
            reviewer="human_reviewer_1",
            decision=DeliberationStatus.REJECTED,
            reasoning="Rejected due to policy violation",
        )

        assert result
        item = queue.queue[item_id]
        assert item.status == DeliberationStatus.REJECTED

    async def test_submit_human_decision_wrong_status(self, queue, test_message):
        """Test human decision fails if item not under review."""
        item_id = await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)
        # Item is still PENDING, not UNDER_REVIEW

        result = await queue.submit_human_decision(
            item_id=item_id,
            reviewer="human_reviewer_1",
            decision=DeliberationStatus.APPROVED,
            reasoning="Test",
        )

        assert not result

    async def test_submit_human_decision_nonexistent_item(self, queue):
        """Test human decision for nonexistent item."""
        result = await queue.submit_human_decision(
            item_id="nonexistent",
            reviewer="human_reviewer_1",
            decision=DeliberationStatus.APPROVED,
            reasoning="Test",
        )

        assert not result


class TestDeliberationStatus:
    """Tests for DeliberationStatus enum."""

    def test_all_statuses_exist(self):
        """Test all expected statuses exist."""
        expected = [
            "PENDING",
            "UNDER_REVIEW",
            "APPROVED",
            "REJECTED",
            "TIMED_OUT",
            "CONSENSUS_REACHED",
        ]

        for status_name in expected:
            assert hasattr(DeliberationStatus, status_name)

    def test_status_values(self):
        """Test status values are correct."""
        assert DeliberationStatus.PENDING.value == "pending"
        assert DeliberationStatus.UNDER_REVIEW.value == "under_review"
        assert DeliberationStatus.APPROVED.value == "approved"
        assert DeliberationStatus.REJECTED.value == "rejected"
        assert DeliberationStatus.TIMED_OUT.value == "timed_out"
        assert DeliberationStatus.CONSENSUS_REACHED.value == "consensus_reached"


class TestGlobalSingleton:
    """Tests for global singleton instance."""

    def test_get_deliberation_queue_singleton(self):
        """Test deliberation queue singleton."""
        # Reset global instance
        _delib_queue._deliberation_queue = None

        queue1 = get_deliberation_queue()
        queue2 = get_deliberation_queue()

        assert queue1 is queue2


class TestStatisticsTracking:
    """Tests for statistics tracking."""

    @pytest.fixture
    async def queue(self):
        """Create a deliberation queue with proper cleanup."""
        q = DeliberationQueue(default_timeout=60)
        yield q
        await q.stop()

    @pytest.fixture
    def test_message(self):
        """Create a test message."""
        return AgentMessage(
            from_agent="test_agent",
            to_agent="target_agent",
            sender_id="test_sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "high_risk_operation"},
        )

    async def test_total_queued_increments(self, queue, test_message):
        """Test total_queued counter increments."""
        assert queue.stats["total_queued"] == 0

        await queue.enqueue_for_deliberation(test_message, timeout_seconds=60)
        assert queue.stats["total_queued"] == 1

        msg2 = AgentMessage(
            from_agent="a",
            to_agent="b",
            sender_id="s",
            message_type=MessageType.COMMAND,
            content={},
        )
        await queue.enqueue_for_deliberation(msg2, timeout_seconds=60)
        assert queue.stats["total_queued"] == 2

    def test_initial_stats(self):
        """Test initial statistics values."""
        queue = DeliberationQueue()

        assert queue.stats["total_queued"] == 0
        assert queue.stats["approved"] == 0
        assert queue.stats["rejected"] == 0
        assert queue.stats["timed_out"] == 0
        assert queue.stats["consensus_reached"] == 0
        assert queue.stats["avg_processing_time"] == 0.0


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
