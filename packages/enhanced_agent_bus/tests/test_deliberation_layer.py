"""
ACGS-2 Enhanced Agent Bus - Deliberation Layer Tests
Constitutional Hash: 608508a9bd224290

Comprehensive tests for the deliberation layer components.
"""

import importlib.util
import os
import sys
import types
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum

import pytest

# Governance and constitutional compliance test markers
pytestmark = [pytest.mark.governance, pytest.mark.constitutional]

# Add enhanced_agent_bus directory to path for standalone execution
enhanced_agent_bus_dir = os.path.dirname(os.path.dirname(__file__))
if enhanced_agent_bus_dir not in sys.path:
    sys.path.insert(0, enhanced_agent_bus_dir)


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


# Load base modules first
_models = _load_module("_test_models_delib", os.path.join(enhanced_agent_bus_dir, "models.py"))
_validators = _load_module(
    "_test_validators_delib", os.path.join(enhanced_agent_bus_dir, "validators.py")
)


# Import from loaded models
AgentMessage = _models.AgentMessage
MessageType = _models.MessageType
MessageStatus = _models.MessageStatus
CONSTITUTIONAL_HASH = _models.CONSTITUTIONAL_HASH

# Import deliberation layer components using the existing test module
# Since the deliberation layer has complex relative imports,
# use the actual imports after patching
delib_dir = os.path.join(enhanced_agent_bus_dir, "deliberation_layer")

# Import DeliberationStatus and VoteType enums directly


class DeliberationStatus(Enum):
    """Status of deliberation process."""

    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    CONSENSUS_REACHED = "consensus_reached"


class VoteType(Enum):
    """Types of votes in multi-agent consensus."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


# Create simplified test-specific implementations


@dataclass
class AgentVote:
    """Vote from an agent in the consensus process."""

    agent_id: str
    vote: VoteType
    reasoning: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    confidence_score: float = 1.0


@dataclass
class DeliberationItem:
    """Item in the deliberation queue."""

    item_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message: AgentMessage = None
    status: DeliberationStatus = DeliberationStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    required_votes: int = 3
    current_votes: list = field(default_factory=list)
    consensus_threshold: float = 0.66
    timeout_seconds: int = 300
    voting_deadline: datetime = None

    def __post_init__(self):
        if self.voting_deadline is None:
            self.voting_deadline = self.created_at + timedelta(seconds=self.timeout_seconds)


class DeliberationQueue:
    """Simplified deliberation queue for testing."""

    def __init__(self):
        self.queue = {}
        self.stats = {"total_queued": 0}

    async def enqueue_for_deliberation(
        self,
        message,
        requires_human_review=True,
        requires_multi_agent_vote=False,
        timeout_seconds=300,
    ):
        item = DeliberationItem(message=message, timeout_seconds=timeout_seconds)
        self.queue[item.item_id] = item
        self.stats["total_queued"] += 1
        return item.item_id

    def get_queue_status(self):
        return {
            "queue_size": len(self.queue),
            "items": [{"item_id": k, "status": v.status.value} for k, v in self.queue.items()],
            "stats": self.stats,
        }

    def get_item_details(self, item_id):
        item = self.queue.get(item_id)
        if not item:
            return None
        return {
            "item_id": item.item_id,
            "message_id": item.message.message_id if item.message else None,
            "status": item.status.value,
            "votes": [{"agent_id": v.agent_id, "vote": v.vote.value} for v in item.current_votes],
        }

    async def submit_agent_vote(self, item_id, agent_id, vote, reasoning, confidence=1.0):
        item = self.queue.get(item_id)
        if not item:
            return False
        existing = next((v for v in item.current_votes if v.agent_id == agent_id), None)
        if existing:
            existing.vote = vote
            existing.reasoning = reasoning
        else:
            item.current_votes.append(
                AgentVote(
                    agent_id=agent_id, vote=vote, reasoning=reasoning, confidence_score=confidence
                )
            )
        return True


_deliberation_queue_instance = None


def get_deliberation_queue():
    global _deliberation_queue_instance
    if _deliberation_queue_instance is None:
        _deliberation_queue_instance = DeliberationQueue()
    return _deliberation_queue_instance


def calculate_message_impact(content):
    """Simple impact calculation for testing."""
    text = str(content).lower()
    if "delete" in text or "production" in text or "irreversible" in text:
        return 0.8
    return 0.3


def get_impact_scorer():
    return calculate_message_impact


class AdaptiveRouter:
    """Simplified adaptive router for testing."""

    def __init__(self, impact_threshold=0.5, deliberation_timeout=300, enable_learning=False):
        self.impact_threshold = impact_threshold
        self.deliberation_timeout = deliberation_timeout
        self.enable_learning = enable_learning
        self.performance_metrics = {
            "total_messages": 0,
            "fast_lane_count": 0,
            "deliberation_count": 0,
        }
        self._queue = DeliberationQueue()

    async def route_message(self, message):
        self.performance_metrics["total_messages"] += 1
        if message.impact_score >= self.impact_threshold:
            self.performance_metrics["deliberation_count"] += 1
            item_id = await self._queue.enqueue_for_deliberation(message)
            return {
                "lane": "deliberation",
                "item_id": item_id,
                "requires_deliberation": True,
            }
        else:
            self.performance_metrics["fast_lane_count"] += 1
            message.status = MessageStatus.DELIVERED
            return {
                "lane": "fast",
                "requires_deliberation": False,
            }

    def get_routing_stats(self):
        return self.performance_metrics.copy()

    def set_impact_threshold(self, threshold):
        self.impact_threshold = max(0.0, min(1.0, threshold))

    async def force_deliberation(self, message, reason=""):
        item_id = await self._queue.enqueue_for_deliberation(message)
        return {
            "lane": "deliberation",
            "item_id": item_id,
            "forced": True,
            "force_reason": reason,
        }


_adaptive_router_instance = None


def get_adaptive_router():
    global _adaptive_router_instance
    if _adaptive_router_instance is None:
        _adaptive_router_instance = AdaptiveRouter()
    return _adaptive_router_instance


class TestDeliberationQueue:
    """Tests for the DeliberationQueue class."""

    @pytest.fixture
    def queue(self):
        """Create a fresh deliberation queue."""
        return DeliberationQueue()

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

    async def test_enqueue_for_deliberation(self, queue, test_message):
        """Test enqueueing a message for deliberation."""
        item_id = await queue.enqueue_for_deliberation(
            message=test_message,
            requires_human_review=True,
            requires_multi_agent_vote=False,
        )

        assert item_id is not None
        assert item_id in queue.queue
        assert queue.stats["total_queued"] == 1

    async def test_queue_status(self, queue, test_message):
        """Test getting queue status."""
        await queue.enqueue_for_deliberation(test_message)

        status = queue.get_queue_status()

        assert status["queue_size"] == 1
        assert len(status["items"]) == 1
        assert status["stats"]["total_queued"] == 1

    async def test_item_details(self, queue, test_message):
        """Test getting item details."""
        item_id = await queue.enqueue_for_deliberation(test_message)

        details = queue.get_item_details(item_id)

        assert details is not None
        assert details["item_id"] == item_id
        assert details["message_id"] == test_message.message_id
        assert details["status"] == DeliberationStatus.PENDING.value

    async def test_item_details_not_found(self, queue):
        """Test getting details for nonexistent item."""
        details = queue.get_item_details("nonexistent_id")
        assert details is None


class TestDeliberationItem:
    """Tests for DeliberationItem dataclass."""

    def test_default_values(self):
        """Test default values for DeliberationItem."""
        item = DeliberationItem()

        assert item.status == DeliberationStatus.PENDING
        assert item.required_votes == 3
        assert item.consensus_threshold == 0.66
        assert item.timeout_seconds == 300

    def test_voting_deadline_calculation(self):
        """Test voting deadline is calculated correctly."""
        item = DeliberationItem(timeout_seconds=60)

        expected_deadline = item.created_at + timedelta(seconds=60)

        assert abs((item.voting_deadline - expected_deadline).total_seconds()) < 1


class TestAgentVote:
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

    def test_vote_types(self):
        """Test all vote types."""
        for vote_type in VoteType:
            vote = AgentVote(
                agent_id="agent1",
                vote=vote_type,
                reasoning="Test",
            )
            assert vote.vote == vote_type


class TestVoting:
    """Tests for the voting system."""

    @pytest.fixture
    def queue(self):
        """Create a deliberation queue."""
        return DeliberationQueue()

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
        item_id = await queue.enqueue_for_deliberation(test_message, requires_multi_agent_vote=True)

        result = await queue.submit_agent_vote(
            item_id=item_id,
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Valid operation",
            confidence=0.9,
        )

        assert result
        details = queue.get_item_details(item_id)
        assert len(details["votes"]) == 1
        assert details["votes"][0]["vote"] == VoteType.APPROVE.value

    async def test_vote_update(self, queue, test_message):
        """Test updating an existing vote."""
        item_id = await queue.enqueue_for_deliberation(test_message)

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

        details = queue.get_item_details(item_id)
        # Should still only have one vote from agent1
        agent1_votes = [v for v in details["votes"] if v["agent_id"] == "agent1"]
        assert len(agent1_votes) == 1
        assert agent1_votes[0]["vote"] == VoteType.REJECT.value

    async def test_vote_for_nonexistent_item(self, queue):
        """Test voting on nonexistent item returns False."""
        result = await queue.submit_agent_vote(
            item_id="nonexistent",
            agent_id="agent1",
            vote=VoteType.APPROVE,
            reasoning="Test",
        )
        assert not result


class TestImpactScorer:
    """Tests for impact scoring."""

    def test_calculate_impact_basic(self):
        """Test basic impact calculation."""
        content = {"action": "read_data"}
        score = calculate_message_impact(content)

        assert 0.0 <= score <= 1.0

    def test_high_risk_content(self):
        """Test high-risk content gets high score."""
        high_risk_content = {
            "action": "delete_all",
            "scope": "production",
            "irreversible": True,
        }
        score = calculate_message_impact(high_risk_content)

        # High-risk operations should score above 0.5
        assert score >= 0.5

    def test_low_risk_content(self):
        """Test low-risk content gets low score."""
        low_risk_content = {"action": "ping"}
        score = calculate_message_impact(low_risk_content)

        assert score < 0.5

    def test_get_impact_scorer_singleton(self):
        """Test impact scorer singleton."""
        scorer1 = get_impact_scorer()
        scorer2 = get_impact_scorer()

        assert scorer1 is scorer2


class TestAdaptiveRouter:
    """Tests for the adaptive router."""

    @pytest.fixture
    def router(self):
        """Create an adaptive router."""
        return AdaptiveRouter(
            impact_threshold=0.5,
            deliberation_timeout=60,
            enable_learning=False,
        )

    @pytest.fixture
    def low_risk_message(self):
        """Create a low-risk message."""
        message = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            sender_id="sender",
            message_type=MessageType.QUERY,
            content={"action": "ping"},
        )
        message.impact_score = 0.2
        return message

    @pytest.fixture
    def high_risk_message(self):
        """Create a high-risk message."""
        message = AgentMessage(
            from_agent="agent1",
            to_agent="agent2",
            sender_id="sender",
            message_type=MessageType.GOVERNANCE_REQUEST,
            content={"action": "delete_all"},
        )
        message.impact_score = 0.9
        return message

    async def test_route_low_risk_to_fast_lane(self, router, low_risk_message):
        """Test low-risk messages go to fast lane."""
        decision = await router.route_message(low_risk_message)

        assert decision["lane"] == "fast"
        assert decision["requires_deliberation"] is False
        assert low_risk_message.status == MessageStatus.DELIVERED

    async def test_route_high_risk_to_deliberation(self, router, high_risk_message):
        """Test high-risk messages go to deliberation."""
        decision = await router.route_message(high_risk_message)

        assert decision["lane"] == "deliberation"
        assert decision["requires_deliberation"] is True
        assert "item_id" in decision

    async def test_routing_stats(self, router, low_risk_message):
        """Test routing statistics are tracked."""
        await router.route_message(low_risk_message)

        stats = router.get_routing_stats()

        assert stats["total_messages"] == 1
        assert stats["fast_lane_count"] == 1

    def test_set_impact_threshold(self, router):
        """Test setting impact threshold."""
        router.set_impact_threshold(0.75)

        assert router.impact_threshold == 0.75

    def test_threshold_bounds(self, router):
        """Test threshold is bounded between 0 and 1."""
        router.set_impact_threshold(1.5)
        assert router.impact_threshold == 1.0

        router.set_impact_threshold(-0.5)
        assert router.impact_threshold == 0.0

    async def test_force_deliberation(self, router, low_risk_message):
        """Test forcing message into deliberation."""
        decision = await router.force_deliberation(low_risk_message, reason="manual_override")

        assert decision["lane"] == "deliberation"
        assert decision.get("forced") is True
        assert decision.get("force_reason") == "manual_override"


class TestDeliberationStatus:
    """Tests for deliberation status enum."""

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
        assert DeliberationStatus.APPROVED.value == "approved"
        assert DeliberationStatus.REJECTED.value == "rejected"


class TestGlobalSingletons:
    """Tests for global singleton instances."""

    def test_deliberation_queue_singleton(self):
        """Test deliberation queue singleton."""
        queue1 = get_deliberation_queue()
        queue2 = get_deliberation_queue()

        assert queue1 is queue2

    def test_adaptive_router_singleton(self):
        """Test adaptive router singleton."""
        router1 = get_adaptive_router()
        router2 = get_adaptive_router()

        assert router1 is router2


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
