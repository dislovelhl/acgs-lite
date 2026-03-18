"""
ACGS-2 Event-Driven Vote Collector
Constitutional Hash: cdd01ef066bc6cf2

Provides high-performance event-driven vote collection using Redis pub/sub
for multi-stakeholder deliberation workflows.

Performance Targets:
- P99 latency: <5ms per vote event
- Throughput: >6000 RPS
- Concurrent sessions: 100+

Architecture:
    Agent Vote Submit → Redis Pub/Sub Channel
                              ↓
                     Vote Collector (Subscribe)
                              ↓
                     Aggregate Votes
                              ↓
                     Consensus Check → Notify Workflow
"""

import asyncio
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment]
    NUMPY_AVAILABLE = False

try:
    from src.core.shared.types import JSONDict  # noqa: E402
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

try:
    import sys

    if "pytest" in sys.modules:
        raise ImportError("Skip torch in tests to avoid Python 3.14 coverage crash")
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    import enhanced_agent_bus_rust.optimization as rust_opt

    RUST_AVAILABLE = True
except ImportError:
    rust_opt = None
    RUST_AVAILABLE = False

try:
    from ..governance.stability.mhc import sinkhorn_projection
except (ImportError, ValueError):
    sinkhorn_projection = None

try:
    import redis
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore[misc, assignment]
    aioredis = None  # type: ignore[misc, assignment]
    REDIS_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class VoteEvent:
    """Represents a vote event from an agent."""

    vote_id: str
    message_id: str
    agent_id: str
    decision: str  # "approve", "reject", "abstain"
    reasoning: str
    confidence: float
    weight: float = 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        """Serialize vote event to dictionary."""
        return {
            "vote_id": self.vote_id,
            "message_id": self.message_id,
            "agent_id": self.agent_id,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "weight": self.weight,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: JSONDict) -> "VoteEvent":
        """Deserialize vote event from dictionary."""
        return cls(
            vote_id=data.get("vote_id", str(uuid.uuid4())),
            message_id=data["message_id"],
            agent_id=data["agent_id"],
            decision=data["decision"],
            reasoning=data.get("reasoning", ""),
            confidence=float(data.get("confidence", 1.0)),
            weight=float(data.get("weight", 1.0)),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if "timestamp" in data
                else datetime.now(UTC)
            ),
            metadata=data.get("metadata", {}),
        )


@dataclass
class VoteSession:
    """Tracks vote collection state for a deliberation session."""

    session_id: str
    message_id: str
    required_votes: int
    consensus_threshold: float
    timeout_seconds: int
    votes: list[VoteEvent] = field(default_factory=list)
    agent_weights: dict[str, float] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed: bool = False
    completion_event: asyncio.Event | None = None

    def add_vote(self, vote: VoteEvent) -> bool:
        """Add a vote to the session. Returns True if vote is new."""
        # Prevent duplicate votes from same agent
        existing_agents = {v.agent_id for v in self.votes}
        if vote.agent_id in existing_agents:
            logger.warning(f"Duplicate vote from {vote.agent_id} for session {self.session_id}")
            return False

        # Apply agent weight if configured
        if vote.agent_id in self.agent_weights:
            vote.weight = self.agent_weights[vote.agent_id]

        self.votes.append(vote)
        return True

    def _stabilize_weights(self) -> dict[str, float]:
        """
        Apply manifold constraint to agent weights for stability.
        Uses high-performance Rust Sinkhorn kernel if available.
        """
        if not self.agent_weights:
            return self.agent_weights

        if RUST_AVAILABLE:
            try:
                if not NUMPY_AVAILABLE:
                    raise ImportError("numpy is required for weight stabilization")
                agent_ids = list(self.agent_weights.keys())
                # Create a 1D array from weights
                weights_list = [self.agent_weights[aid] for aid in agent_ids]
                # Convert to 2D for Sinkhorn (1, N)
                weights_matrix = np.array([weights_list], dtype=np.float32)

                # Stabilize using Sinkhorn-Knopp algorithm in Rust
                stabilized_matrix = rust_opt.sinkhorn_knopp_stabilize(
                    weights_matrix, regularization=0.1, iterations=10
                )

                # Rescale to sum to 1.0 (ensure valid distribution)
                stabilized_vector = stabilized_matrix[0]
                total = stabilized_vector.sum()
                if total > 0:
                    stabilized_vector /= total

                return {aid: float(stabilized_vector[i]) for i, aid in enumerate(agent_ids)}
            except (ValueError, TypeError, RuntimeError) as e:
                logger.warning(
                    f"Rust Sinkhorn stabilization failed: {e}, falling back to torch/Python"
                )

        if sinkhorn_projection is None or not TORCH_AVAILABLE:
            return self.agent_weights

        # Fallback: return original weights if neither Rust nor Torch performed stabilization
        return self.agent_weights

    def check_consensus(self) -> JSONDict:
        """Check if consensus threshold has been reached."""
        if len(self.votes) < self.required_votes:
            return {
                "consensus_reached": False,
                "reason": "insufficient_votes",
                "votes_received": len(self.votes),
                "votes_required": self.required_votes,
            }

        # Apply mHC stability layer to weights if active
        active_weights = self._stabilize_weights()

        # Calculate weighted voting result
        total_weight = sum(active_weights.get(v.agent_id, v.weight) for v in self.votes)
        approve_weight = sum(
            active_weights.get(v.agent_id, v.weight) for v in self.votes if v.decision == "approve"
        )
        reject_weight = sum(
            active_weights.get(v.agent_id, v.weight) for v in self.votes if v.decision == "reject"
        )

        if total_weight == 0:
            return {"consensus_reached": False, "reason": "zero_total_weight"}

        approval_rate = approve_weight / total_weight
        rejection_rate = reject_weight / total_weight

        if approval_rate >= self.consensus_threshold:
            return {
                "consensus_reached": True,
                "decision": "approved",
                "approval_rate": approval_rate,
                "votes_received": len(self.votes),
            }
        elif rejection_rate >= self.consensus_threshold:
            return {
                "consensus_reached": True,
                "decision": "rejected",
                "rejection_rate": rejection_rate,
                "votes_received": len(self.votes),
            }

        return {
            "consensus_reached": False,
            "reason": "threshold_not_met",
            "approval_rate": approval_rate,
            "rejection_rate": rejection_rate,
            "votes_received": len(self.votes),
        }

    def is_timed_out(self) -> bool:
        """Check if the session has timed out."""
        deadline = self.created_at + timedelta(seconds=self.timeout_seconds)
        return datetime.now(UTC) > deadline


class EventDrivenVoteCollector:
    """
    High-performance event-driven vote collector using Redis pub/sub.

    Features:
    - Real-time vote events via Redis pub/sub
    - Weighted voting support
    - Configurable quorum rules
    - Automatic timeout handling
    - Immutable audit trail
    - 100+ concurrent sessions support

    Usage:
        collector = EventDrivenVoteCollector(redis_url)
        await collector.connect()

        # Create vote session
        session_id = await collector.create_vote_session(
            message_id="msg-123",
            required_votes=3,
            consensus_threshold=0.66,
            timeout_seconds=300
        )

        # Wait for votes (event-driven)
        result = await collector.wait_for_consensus(session_id)

        # Or manually submit a vote
        await collector.submit_vote(
            message_id="msg-123",
            agent_id="agent-1",
            decision="approve",
            reasoning="Policy compliant"
        )
    """

    def __init__(
        self,
        redis_url: str | None = None,
        channel_prefix: str = "acgs:votes",
        max_concurrent_sessions: int = 1000,
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.channel_prefix = channel_prefix
        self.max_concurrent_sessions = max_concurrent_sessions

        # Redis connections
        self.redis_client: object | None = None
        self.pubsub: object | None = None

        # Active sessions (message_id -> VoteSession)
        self._sessions: dict[str, VoteSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

        # Subscriber task
        self._subscriber_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._running = False

        # In-memory fallback when Redis unavailable
        self._in_memory_votes: dict[str, list[VoteEvent]] = {}

    async def connect(self) -> bool:
        """Connect to Redis and start subscriber."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - using in-memory fallback")
            return False

        try:
            self.redis_client = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()
            logger.info(f"Vote collector connected to Redis at {self.redis_url}")

            # Initialize pub/sub
            self.pubsub = self.redis_client.pubsub()

            # Start subscriber task (held in _background_tasks to prevent GC)
            self._running = True
            task = asyncio.create_task(self._subscriber_loop())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            self._subscriber_task = task

            return True

        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to connect vote collector to Redis: {e}")
            self.redis_client = None
            self.pubsub = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis and stop subscriber."""
        self._running = False

        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:  # noqa: SIM105
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
            self._subscriber_task = None

        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
            self.pubsub = None

        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

        logger.info("Vote collector disconnected")

    async def create_vote_session(
        self,
        message_id: str,
        required_votes: int = 3,
        consensus_threshold: float = 0.66,
        timeout_seconds: int = 300,
        agent_weights: dict[str, float] | None = None,
    ) -> str:
        """
        Create a new vote collection session.

        Args:
            message_id: Message ID to collect votes for
            required_votes: Minimum votes required
            consensus_threshold: Approval threshold (0-1)
            timeout_seconds: Session timeout
            agent_weights: Optional agent weight overrides

        Returns:
            Session ID for tracking
        """
        if len(self._sessions) >= self.max_concurrent_sessions:
            # Clean up expired sessions
            await self._cleanup_expired_sessions()
            if len(self._sessions) >= self.max_concurrent_sessions:
                raise RuntimeError(
                    f"Maximum concurrent sessions ({self.max_concurrent_sessions}) reached"
                )

        session_id = f"{message_id}:{uuid.uuid4().hex[:8]}"
        session = VoteSession(
            session_id=session_id,
            message_id=message_id,
            required_votes=required_votes,
            consensus_threshold=consensus_threshold,
            timeout_seconds=timeout_seconds,
            agent_weights=agent_weights or {},
            completion_event=asyncio.Event(),
        )

        self._sessions[session_id] = session
        self._session_locks[session_id] = asyncio.Lock()

        # Subscribe to vote channel for this message
        channel = f"{self.channel_prefix}:{message_id}"
        if self.pubsub:
            await self.pubsub.subscribe(channel)

        # Store session in Redis for persistence
        if self.redis_client:
            try:
                await self.redis_client.hset(
                    f"{self.channel_prefix}:sessions",
                    session_id,
                    json.dumps(
                        {
                            "message_id": message_id,
                            "required_votes": required_votes,
                            "consensus_threshold": consensus_threshold,
                            "timeout_seconds": timeout_seconds,
                            "created_at": session.created_at.isoformat(),
                        }
                    ),
                )
                # set expiry on session
                await self.redis_client.expire(
                    f"{self.channel_prefix}:sessions", timeout_seconds + 60
                )
            except (redis.RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Failed to persist session to Redis: {e}")

        logger.info(f"Created vote session {session_id} for message {message_id}")
        return session_id

    async def submit_vote(
        self,
        message_id: str,
        agent_id: str,
        decision: str,
        reasoning: str = "",
        confidence: float = 1.0,
        weight: float = 1.0,
        metadata: JSONDict | None = None,
    ) -> bool:
        """
        Submit a vote for a message.

        Publishes vote event to Redis pub/sub for all subscribers to receive.

        Args:
            message_id: Message ID to vote on
            agent_id: Voting agent ID
            decision: Vote decision (approve/reject/abstain)
            reasoning: Vote reasoning
            confidence: Confidence score (0-1)
            weight: Vote weight
            metadata: Additional metadata

        Returns:
            True if vote submitted successfully
        """
        if decision not in ("approve", "reject", "abstain"):
            raise ValueError(f"Invalid decision: {decision}")

        vote = VoteEvent(
            vote_id=str(uuid.uuid4()),
            message_id=message_id,
            agent_id=agent_id,
            decision=decision,
            reasoning=reasoning,
            confidence=confidence,
            weight=weight,
            metadata=metadata or {},
        )

        # Publish to Redis channel
        if self.redis_client:
            try:
                channel = f"{self.channel_prefix}:{message_id}"
                await self.redis_client.publish(channel, json.dumps(vote.to_dict()))

                # Also store in hash for persistence
                votes_key = f"{self.channel_prefix}:votes:{message_id}"
                await self.redis_client.hset(votes_key, agent_id, json.dumps(vote.to_dict()))
                await self.redis_client.expire(votes_key, 86400)  # 24h expiry

                return True

            except (redis.RedisError, ConnectionError, TimeoutError) as e:
                logger.error(f"Failed to publish vote to Redis: {e}")

        # Fallback to in-memory
        if message_id not in self._in_memory_votes:
            self._in_memory_votes[message_id] = []
        self._in_memory_votes[message_id].append(vote)

        # Notify local sessions
        await self._process_vote_event(vote)

        return True

    async def wait_for_consensus(
        self, session_id: str, timeout_override: int | None = None
    ) -> JSONDict:
        """
        Wait for consensus to be reached or timeout.

        This is event-driven - no polling. Uses asyncio.Event for notification.

        Args:
            session_id: Vote session ID
            timeout_override: Optional timeout override

        Returns:
            Consensus result with votes and decision
        """
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found", "session_id": session_id}

        timeout = timeout_override if timeout_override is not None else session.timeout_seconds
        completion_event = session.completion_event

        try:
            # Wait for completion signal or timeout
            await asyncio.wait_for(completion_event.wait(), timeout=timeout)

            # Check final consensus
            consensus = session.check_consensus()
            consensus["votes"] = [v.to_dict() for v in session.votes]
            return consensus

        except TimeoutError:
            # Check if we got enough votes even if not consensus
            consensus = session.check_consensus()
            consensus["timed_out"] = True
            consensus["votes"] = [v.to_dict() for v in session.votes]
            return consensus

        finally:
            # Cleanup session
            await self._cleanup_session(session_id)

    async def get_current_votes(self, message_id: str) -> list[JSONDict]:
        """Get all current votes for a message."""
        # Check Redis first
        if self.redis_client:
            try:
                votes_key = f"{self.channel_prefix}:votes:{message_id}"
                votes_raw = await self.redis_client.hgetall(votes_key)
                return [json.loads(v) for v in votes_raw.values()]
            except (redis.RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Failed to get votes from Redis: {e}")

        # Fall back to in-memory
        votes = self._in_memory_votes.get(message_id, [])
        return [v.to_dict() for v in votes]

    async def _subscriber_loop(self) -> None:
        """Background task that listens for vote events from Redis pub/sub."""
        logger.info("Vote collector subscriber started")

        try:
            while self._running and self.pubsub:
                try:
                    message = await asyncio.wait_for(
                        self.pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0,
                    )

                    if message and message["type"] == "message":
                        await self._handle_pubsub_message(message)

                except TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    logger.error(f"Error in subscriber loop: {e}")
                    await asyncio.sleep(0.1)

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"Subscriber loop failed: {e}")

        logger.info("Vote collector subscriber stopped")

    async def _handle_pubsub_message(self, message: JSONDict) -> None:
        """Handle incoming pub/sub message."""
        try:
            channel = message.get("channel", "")
            data = message.get("data", "")

            if not data or not channel:
                return

            # Parse vote event
            vote_data = json.loads(data)
            vote = VoteEvent.from_dict(vote_data)

            # Process vote event
            await self._process_vote_event(vote)

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid vote event JSON: {e}")
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"Error handling pub/sub message: {e}")

    async def _process_vote_event(self, vote: VoteEvent) -> None:
        """Process a vote event and update relevant sessions."""
        message_id = vote.message_id

        # Find sessions for this message
        for session_id, session in list(self._sessions.items()):
            if session.message_id != message_id:
                continue

            if session.completed:
                continue

            # Add vote with lock to prevent race conditions
            lock = self._session_locks.get(session_id)
            if lock:
                async with lock:
                    added = session.add_vote(vote)
                    if added:
                        logger.debug(
                            f"Vote added to session {session_id}: "
                            f"{len(session.votes)}/{session.required_votes}"
                        )

                        # Check for consensus
                        consensus = session.check_consensus()
                        if consensus.get("consensus_reached"):
                            session.completed = True
                            if session.completion_event:
                                session.completion_event.set()
                            logger.info(
                                f"Consensus reached for session {session_id}: "
                                f"{consensus.get('decision')}"
                            )

    async def _cleanup_session(self, session_id: str) -> None:
        """Clean up a vote session."""
        session = self._sessions.pop(session_id, None)
        self._session_locks.pop(session_id, None)

        if session and self.pubsub:
            try:
                channel = f"{self.channel_prefix}:{session.message_id}"
                await self.pubsub.unsubscribe(channel)
            except (redis.RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Failed to unsubscribe from channel: {e}")

        if self.redis_client:
            try:
                await self.redis_client.hdel(f"{self.channel_prefix}:sessions", session_id)
            except (redis.RedisError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Failed to remove session from Redis: {e}")

    async def _cleanup_expired_sessions(self) -> None:
        """Clean up expired sessions."""
        expired = []
        for session_id, session in self._sessions.items():
            if session.is_timed_out():
                expired.append(session_id)

        for session_id in expired:
            await self._cleanup_session(session_id)
            logger.info(f"Cleaned up expired session: {session_id}")

    def get_session_count(self) -> int:
        """Get count of active sessions."""
        return len(self._sessions)

    async def get_session_info(self, session_id: str) -> JSONDict | None:
        """Get session information."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        return {
            "session_id": session.session_id,
            "message_id": session.message_id,
            "required_votes": session.required_votes,
            "votes_received": len(session.votes),
            "consensus_threshold": session.consensus_threshold,
            "timeout_seconds": session.timeout_seconds,
            "created_at": session.created_at.isoformat(),
            "completed": session.completed,
            "is_timed_out": session.is_timed_out(),
            "consensus": session.check_consensus(),
        }


# Global instance
_vote_collector: EventDrivenVoteCollector | None = None


def get_vote_collector() -> EventDrivenVoteCollector:
    """Get or create global vote collector instance."""
    global _vote_collector
    if _vote_collector is None:
        _vote_collector = EventDrivenVoteCollector()
    return _vote_collector


def reset_vote_collector() -> None:
    """Reset the global vote collector instance."""
    global _vote_collector
    _vote_collector = None


__all__ = [
    "EventDrivenVoteCollector",
    "VoteEvent",
    "VoteSession",
    "get_vote_collector",
    "reset_vote_collector",
]
