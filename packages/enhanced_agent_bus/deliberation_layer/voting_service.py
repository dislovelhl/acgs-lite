"""
ACGS-2 Deliberation Layer - Voting Service
Constitutional Hash: cdd01ef066bc6cf2
Enables multi-agent consensus for high-impact decisions.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from enum import Enum
from typing import cast

from src.core.shared.types import JSONDict, JSONValue

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    from packages.enhanced_agent_bus.models import CONSTITUTIONAL_HASH, AgentMessage
except ImportError:
    # Fallback for when running in isolation or different structure
    from packages.enhanced_agent_bus.models import (  # type: ignore[import-untyped]
        CONSTITUTIONAL_HASH,
        AgentMessage,
    )

try:
    from packages.enhanced_agent_bus.deliberation_layer.redis_election_store import (
        RedisElectionStore,
        get_election_store,
    )
except ImportError:
    RedisElectionStore = None  # type: ignore[misc, assignment]
    get_election_store = None  # type: ignore[misc, assignment]

try:
    from src.core.shared.config import settings
except ImportError:
    # Fallback to local config or mock
    settings = None

logger = get_logger(__name__)
_VOTING_SERVICE_ERRORS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ConnectionError,
    OSError,
)
ELECTION_STORE_INIT_ERRORS = _VOTING_SERVICE_ERRORS
VOTE_EVENT_PUBLISH_ERRORS = _VOTING_SERVICE_ERRORS


class VotingStrategy(Enum):
    QUORUM = "quorum"  # 50% + 1
    UNANIMOUS = "unanimous"  # 100%
    SUPER_MAJORITY = "super-majority"  # 2/3


@dataclass
class Vote:
    agent_id: str
    decision: str  # "APPROVE", "DENY", "ABSTAIN"
    reason: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Election:
    election_id: str
    message_id: str
    strategy: VotingStrategy
    participants: set[str]
    votes: dict[str, Vote] = field(default_factory=dict)
    status: str = "OPEN"  # OPEN, CLOSED, EXPIRED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class ElectionProxy:
    """Proxy class that provides attribute access to election dict for backward compat."""

    def __init__(self, data: JSONDict):
        self._data = data

    def __getattr__(self, name: str) -> object:
        if name == "_data":
            return object.__getattribute__(self, "_data")
        data = object.__getattribute__(self, "_data")
        if name == "strategy":
            # Convert string to enum
            val = data.get("strategy", "quorum")
            return VotingStrategy(val) if isinstance(val, str) else val
        if name == "participants":
            # Convert to set
            return set(data.get("participants", []))
        if name == "votes":
            # Convert vote dicts to Vote objects
            votes_data = data.get("votes", {})
            return {k: Vote(**v) if isinstance(v, dict) else v for k, v in votes_data.items()}
        return data.get(name)


class ElectionsDict(dict):
    """Dict wrapper that returns ElectionProxy objects for backward compat."""

    def __getitem__(self, key: str) -> ElectionProxy:
        raw = super().__getitem__(key)
        return ElectionProxy(raw) if isinstance(raw, dict) else raw


class VotingService:
    """
    Manages multi-agent voting on high-impact messages.

    Uses Redis for persistent storage of elections and votes.
    """

    def __init__(
        self,
        default_strategy: VotingStrategy = VotingStrategy.QUORUM,
        election_store: RedisElectionStore | None = None,
        kafka_bus: object | None = None,
        force_in_memory: bool = False,
    ):
        self.default_strategy = default_strategy
        self.election_store = election_store
        self.kafka_bus = kafka_bus
        self._force_in_memory = force_in_memory
        # If force_in_memory is True, mark as initialized to skip Redis connection
        self._store_initialized = force_in_memory
        # Initialize in-memory elections storage for backward compatibility
        self._in_memory_elections: dict[str, JSONDict] = {}

    @property
    def elections(self) -> ElectionsDict:
        """Return in-memory elections with Election-like access for backward compatibility."""
        wrapped = ElectionsDict(self._in_memory_elections)
        return wrapped

    async def _ensure_store_initialized(self) -> bool:
        """Ensure Redis election store is initialized."""
        if self._store_initialized:
            return self.election_store is not None

        if self.election_store is None:
            if get_election_store is None:
                logger.warning("RedisElectionStore not available, using in-memory fallback")
                return False
            try:
                self.election_store = await get_election_store()
                self._store_initialized = True
                return True
            except ELECTION_STORE_INIT_ERRORS as e:
                logger.error(f"Failed to initialize election store: {e}")
                return False

        self._store_initialized = True
        return True

    async def create_election(
        self,
        message: AgentMessage,
        participants: list[str],
        timeout: int | None = None,
        participant_weights: dict[str, float] | None = None,
    ) -> str:
        """
        Create a new voting process for a high-impact message.

        Args:
            message: AgentMessage to vote on
            participants: List of agent IDs participating in the election
            timeout: Timeout in seconds (defaults to settings.voting.default_timeout_seconds)
            participant_weights: Optional dict mapping agent_id to vote weight (defaults to 1.0 for all)

        Returns:
            Election ID string
        """  # noqa: E501
        if timeout is None:
            if settings is None or not hasattr(settings, "voting"):
                timeout = 300  # Default 5-minute timeout when settings unavailable
                logger.warning("Voting settings unavailable, using default timeout=%d", timeout)
            else:
                timeout = settings.voting.default_timeout_seconds

        election_id = str(uuid.uuid4())
        created_at = datetime.now(UTC)
        expires_at = datetime.fromtimestamp(created_at.timestamp() + timeout, tz=UTC)

        # Build participant weights dict (default 1.0 for all)
        weights = participant_weights or {}
        participant_weights_dict = {pid: weights.get(pid, 1.0) for pid in participants}

        # Get tenant_id from message
        tenant_id = getattr(message, "tenant_id", None) or "default"

        election_data = {
            "election_id": election_id,
            "message_id": message.message_id,
            "tenant_id": tenant_id,
            "strategy": self.default_strategy.value,
            "participants": list(participants),
            "participant_weights": participant_weights_dict,
            "votes": {},
            "status": "OPEN",
            "created_at": created_at,
            "expires_at": expires_at,
        }

        # Save to Redis if available
        if await self._ensure_store_initialized():
            success = await self.election_store.save_election(election_id, election_data, timeout)
            if not success:
                logger.warning(
                    f"Failed to save election {election_id} to Redis, using in-memory fallback"
                )
                # Fallback to in-memory (for backward compatibility during migration)
                if not hasattr(self, "_in_memory_elections"):
                    self._in_memory_elections: dict[str, JSONDict] = {}  # type: ignore[no-redef]
                self._in_memory_elections[election_id] = election_data
        else:
            # In-memory fallback
            if not hasattr(self, "_in_memory_elections"):
                self._in_memory_elections: dict[str, JSONDict] = {}  # type: ignore[no-redef]
            self._in_memory_elections[election_id] = election_data

        logger.info(f"Election {election_id} created for message {message.message_id}")
        return election_id

    async def cast_vote(self, election_id: str, vote: Vote) -> bool:
        """
        Cast a vote in an election.

        Note: This method stores the vote in Redis but does NOT publish to Kafka.
        Kafka publishing should be done by the caller (e.g., VoteEventConsumer).
        """
        # Validate vote eligibility
        election_data = await self._validate_vote_eligibility(election_id, vote)
        if not election_data:
            return False

        # Prepare vote data for storage
        vote_dict = self._prepare_vote_dict(vote)

        # Publish to Kafka if available
        await self._publish_vote_event(election_id, vote, election_data, vote_dict)

        # Store vote in Redis or in-memory
        await self._store_vote(election_id, vote_dict)

        logger.info(f"Agent {vote.agent_id} cast {vote.decision} for election {election_id}")

        # Check if election can be resolved early
        await self._check_resolution(election_id)
        return True

    async def _validate_vote_eligibility(self, election_id: str, vote: Vote) -> JSONDict | None:
        """Validate that a vote can be cast in the given election."""
        election_data = await self._get_election_data(election_id)
        if not election_data:
            logger.warning(f"Election {election_id} not found")
            return None

        if election_data.get("status") != "OPEN":
            logger.warning(
                f"Election {election_id} is not OPEN (status: {election_data.get('status')})"
            )
            return None

        participants = election_data.get("participants", [])
        if vote.agent_id not in participants:
            logger.warning(f"Agent {vote.agent_id} is not a participant in election {election_id}")
            return None

        return election_data

    @staticmethod
    def _prepare_vote_dict(vote: Vote) -> JSONDict:
        """Convert Vote dataclass to dict for storage."""
        return {
            "agent_id": vote.agent_id,
            "decision": vote.decision,
            "reason": vote.reason,
            "timestamp": (
                vote.timestamp.isoformat()
                if isinstance(vote.timestamp, datetime)
                else vote.timestamp
            ),
        }

    async def _publish_vote_event(
        self, election_id: str, vote: Vote, election_data: JSONDict, vote_dict: JSONDict
    ) -> None:
        """Publish vote event to Kafka if bus is available."""
        if not self.kafka_bus:
            return

        tenant_id = election_data.get("tenant_id", "default")
        vote_event_dict = {
            "election_id": election_id,
            "agent_id": vote.agent_id,
            "decision": vote.decision,
            "weight": election_data.get("participant_weights", {}).get(vote.agent_id, 1.0),
            "reasoning": vote.reason,
            "confidence": 1.0,  # Default confidence
            "timestamp": vote_dict["timestamp"],
        }

        try:
            success = await self.kafka_bus.publish_vote_event(tenant_id, vote_event_dict)
            if not success:
                logger.warning(
                    f"Failed to publish vote event to Kafka for election {election_id}, continuing anyway"  # noqa: E501
                )
        except VOTE_EVENT_PUBLISH_ERRORS as e:
            logger.error(f"Error publishing vote event to Kafka: {e}")
            # Continue with Redis update even if Kafka fails (fail-safe)

    async def _store_vote(self, election_id: str, vote_dict: JSONDict) -> None:
        """Store vote in Redis or in-memory fallback."""
        if await self._ensure_store_initialized() and self.election_store:
            success = await self.election_store.add_vote(election_id, vote_dict)
            if not success:
                logger.warning(f"Failed to add vote to Redis for election {election_id}")
                self._store_vote_in_memory(election_id, vote_dict)
        else:
            self._store_vote_in_memory(election_id, vote_dict)

    def _store_vote_in_memory(self, election_id: str, vote_dict: JSONDict) -> None:
        """Store vote in in-memory fallback."""
        if hasattr(self, "_in_memory_elections") and election_id in self._in_memory_elections:
            self._in_memory_elections[election_id].setdefault("votes", {})[
                vote_dict["agent_id"]
            ] = vote_dict

    async def _get_election_data(self, election_id: str) -> JSONDict | None:
        """Get election data from Redis or in-memory fallback."""
        if await self._ensure_store_initialized() and self.election_store:
            election_data = await self.election_store.get_election(election_id)
            if election_data:
                return election_data

        # Fallback to in-memory
        if hasattr(self, "_in_memory_elections"):
            return self._in_memory_elections.get(election_id)

        return None

    async def _check_resolution(self, election_id: str) -> None:
        """
        Check if an election can be resolved based on its strategy.

        Supports weighted voting: votes are weighted by participant weight.
        """
        election_data = await self._get_election_data(election_id)
        if not election_data:
            return

        strategy = self._get_voting_strategy(election_data)
        weight_info = self._calculate_vote_weights(election_data)

        resolved, decision = self._evaluate_strategy_resolution(strategy, weight_info)

        if resolved:
            await self._finalize_election_result(election_id, election_data, decision)

    def _get_voting_strategy(self, election_data: JSONDict) -> VotingStrategy:
        """Get the voting strategy for the election."""
        strategy_str = election_data.get("strategy", self.default_strategy.value)
        try:
            return VotingStrategy(strategy_str)
        except ValueError:
            return self.default_strategy

    def _calculate_vote_weights(self, election_data: JSONDict) -> tuple[float, float, float]:
        """Calculate weighted vote totals: (approvals_weight, denials_weight, total_weight)."""
        participants = election_data.get("participants", [])
        participant_weights = election_data.get("participant_weights", {})
        votes = election_data.get("votes", {})

        approvals_weight = sum(
            participant_weights.get(vote.get("agent_id", ""), 1.0)
            for vote in votes.values()
            if vote.get("decision") == "APPROVE"
        )
        denials_weight = sum(
            participant_weights.get(vote.get("agent_id", ""), 1.0)
            for vote in votes.values()
            if vote.get("decision") == "DENY"
        )
        total_weight = sum(participant_weights.get(pid, 1.0) for pid in participants)

        return approvals_weight, denials_weight, total_weight

    @staticmethod
    def _evaluate_strategy_resolution(
        strategy: VotingStrategy, weight_info: tuple[float, float, float]
    ) -> tuple[bool, str]:
        """Evaluate if an election should be resolved based on strategy and weights."""
        approvals_weight, denials_weight, total_weight = weight_info

        if strategy == VotingStrategy.QUORUM:
            return VotingService._check_quorum_resolution(
                approvals_weight, denials_weight, total_weight
            )
        elif strategy == VotingStrategy.UNANIMOUS:
            return VotingService._check_unanimous_resolution(
                approvals_weight, denials_weight, total_weight
            )
        elif strategy == VotingStrategy.SUPER_MAJORITY:
            return VotingService._check_super_majority_resolution(
                approvals_weight, denials_weight, total_weight
            )

        return False, "DENY"

    @staticmethod
    def _check_quorum_resolution(
        approvals: float, denials: float, total: float
    ) -> tuple[bool, str]:
        """Check quorum (50% + 1) resolution."""
        if approvals > total / 2:
            return True, "APPROVE"
        elif denials >= total / 2:
            return True, "DENY"
        return False, "DENY"

    @staticmethod
    def _check_unanimous_resolution(
        approvals: float, denials: float, total: float
    ) -> tuple[bool, str]:
        """Check unanimous resolution."""
        if approvals >= total:
            return True, "APPROVE"
        elif denials > 0:
            return True, "DENY"
        return False, "DENY"

    @staticmethod
    def _check_super_majority_resolution(
        approvals: float, denials: float, total: float
    ) -> tuple[bool, str]:
        """Check super-majority (2/3) resolution."""
        if approvals >= (total * 2 / 3):
            return True, "APPROVE"
        elif denials > (total / 3):
            return True, "DENY"
        return False, "DENY"

    async def _finalize_election_result(
        self, election_id: str, election_data: JSONDict, decision: str
    ) -> None:
        """Finalize election with result and update storage."""
        election_data["status"] = "CLOSED"
        election_data["result"] = decision
        election_data["resolved_at"] = datetime.now(UTC).isoformat()

        # Update Redis or in-memory
        if await self._ensure_store_initialized() and self.election_store:
            ttl = (
                settings.voting.default_timeout_seconds
                if settings is not None and hasattr(settings, "voting")
                else 300
            )
            await self.election_store.update_election_status(election_id, "CLOSED")
            await self.election_store.save_election(election_id, election_data, ttl)
        elif hasattr(self, "_in_memory_elections") and election_id in self._in_memory_elections:
            self._in_memory_elections[election_id] = election_data

        logger.info(f"Election {election_id} resolved with decision: {decision}")

    async def get_result(self, election_id: str) -> str | None:
        """Get the decision result of an election."""
        election_data = await self._get_election_data(election_id)
        if not election_data:
            return None

        # Check and update expiration status
        status = await self._check_and_update_expiration(election_id, election_data)

        # Handle results based on status
        return await self._get_result_by_status(election_id, election_data, status)

    async def _check_and_update_expiration(self, election_id: str, election_data: JSONDict) -> str:
        """Check if election has expired and update status if needed."""
        status = election_data.get("status", "OPEN")
        expires_at_str = election_data.get("expires_at")

        if status != "OPEN" or not expires_at_str:
            return status  # type: ignore[no-any-return]

        try:
            expires_at = self._parse_expires_at(expires_at_str)
            if datetime.now(UTC) > expires_at:
                await self._mark_election_expired(election_id, election_data)
                return "EXPIRED"
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse expires_at for election {election_id}: {e}")

        return status  # type: ignore[no-any-return]

    @staticmethod
    def _parse_expires_at(expires_at_str: object) -> datetime:
        """Parse expires_at string to datetime."""
        if isinstance(expires_at_str, str):
            return datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        else:
            return cast(datetime, expires_at_str)

    async def _mark_election_expired(self, election_id: str, election_data: JSONDict) -> None:
        """Mark election as expired and update storage."""
        election_data["status"] = "EXPIRED"

        if await self._ensure_store_initialized() and self.election_store:
            await self.election_store.update_election_status(election_id, "EXPIRED")
        elif hasattr(self, "_in_memory_elections") and election_id in self._in_memory_elections:
            self._in_memory_elections[election_id]["status"] = "EXPIRED"

        logger.info(f"Election {election_id} expired.")

    async def _get_result_by_status(
        self, election_id: str, election_data: JSONDict, status: str
    ) -> str | None:
        """Get result based on election status."""
        if status == "EXPIRED":
            return "DENY"

        if status == "CLOSED":
            return await self._get_closed_election_result(election_id, election_data)

        return None

    async def _get_closed_election_result(
        self, election_id: str, election_data: JSONDict
    ) -> str | None:
        """Get result for closed election with fallback recalculation."""
        result = election_data.get("result")
        if result:
            return cast(str, result)

        # Fallback recalculation (shouldn't happen in production)
        logger.warning(f"Election {election_id} is CLOSED but has no stored result, recalculating")
        await self._check_resolution(election_id)
        election_data = await self._get_election_data(election_id)
        return cast(str | None, election_data.get("result")) if election_data else None
