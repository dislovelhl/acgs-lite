"""
ACGS-2 Deliberation Layer - Redis Election Store
Constitutional Hash: 608508a9bd224290

Redis-backed persistent storage for elections and votes.
Replaces in-memory storage with distributed, persistent storage.
"""

import json
from datetime import datetime, timezone
from typing import cast

try:
    from src.core.shared.types import JSONDict
except ImportError:
    JSONDict = dict  # type: ignore[misc,assignment]

from enhanced_agent_bus.observability.structured_logging import get_logger

try:
    import redis.asyncio as aioredis

    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

try:
    from src.core.shared.config import settings
except ImportError:
    from src.core.shared.config import settings  # type: ignore[import-untyped]

logger = get_logger(__name__)


class RedisElectionStore:
    """
    Redis-backed storage for elections and votes.

    Provides persistent, distributed storage for voting elections
    with TTL support for automatic expiration.
    """

    def __init__(self, redis_url: str | None = None, election_prefix: str | None = None):
        """
        Initialize Redis election store.

        Args:
            redis_url: Redis connection URL (defaults to settings.redis.url)
            election_prefix: Redis key prefix for elections (defaults to settings.voting.redis_election_prefix)
        """
        self.redis_url = redis_url or settings.redis.url
        self.election_prefix = election_prefix or settings.voting.redis_election_prefix
        self.redis_client: object | None = None

    async def connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, election storage will fail")
            return False

        try:
            self.redis_client = aioredis.from_url(
                self.redis_url, encoding="utf-8", decode_responses=True
            )
            await self.redis_client.ping()
            logger.info(f"RedisElectionStore connected to {self.redis_url}")
            return True
        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
            return False

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
            logger.info("RedisElectionStore disconnected")

    def _get_election_key(self, election_id: str) -> str:
        """Get Redis key for an election."""
        return f"{self.election_prefix}{election_id}"

    async def save_election(self, election_id: str, election_data: JSONDict, ttl: int) -> bool:
        """
        Save an election to Redis with TTL.

        Args:
            election_id: Unique election identifier
            election_data: Election data dictionary (must be JSON-serializable)
            ttl: Time-to-live in seconds

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.redis_client:
            logger.error("Redis client not connected")
            return False

        try:
            key = self._get_election_key(election_id)
            # Serialize datetime objects
            serialized_data = self._serialize_election_data(election_data)
            json_str = json.dumps(serialized_data, default=str)

            await self.redis_client.setex(key, ttl, json_str)

            return True
        except (ConnectionError, OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to save election {election_id}: {e}")
            return False

    async def get_election(self, election_id: str) -> JSONDict | None:
        """
        Get an election from Redis.

        Args:
            election_id: Unique election identifier

        Returns:
            Election data dictionary or None if not found
        """
        if not self.redis_client:
            logger.error("Redis client not connected")
            return None

        try:
            key = self._get_election_key(election_id)
            json_str = await self.redis_client.get(key)
            if not json_str:
                return None

            data = json.loads(json_str)
            return self._deserialize_election_data(data)
        except (ConnectionError, OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to get election {election_id}: {e}")
            return None

    async def add_vote(self, election_id: str, vote: JSONDict) -> bool:
        """
        Add a vote to an election in Redis.

        Args:
            election_id: Unique election identifier
            vote: Vote data dictionary (must include agent_id)

        Returns:
            True if vote added successfully, False otherwise
        """
        if not self.redis_client:
            logger.error("Redis client not connected")
            return False

        try:
            # Load election
            election = await self.get_election(election_id)
            if not election:
                logger.warning(f"Election {election_id} not found")
                return False

            # Add vote to votes dict
            if "votes" not in election:
                election["votes"] = {}

            agent_id = vote.get("agent_id")
            if not agent_id:
                logger.error("Vote missing agent_id")
                return False

            election["votes"][agent_id] = vote

            # Get remaining TTL
            key = self._get_election_key(election_id)
            ttl = await self.redis_client.ttl(key)
            if ttl <= 0:
                ttl = settings.voting.default_timeout_seconds

            # Save updated election
            serialized = self._serialize_election_data(election)
            json_str = json.dumps(serialized, default=str)
            await self.redis_client.setex(key, ttl, json_str)

            return True
        except (ConnectionError, OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to add vote to election {election_id}: {e}")
            return False

    async def get_votes(self, election_id: str) -> list[JSONDict]:
        """
        Get all votes for an election.

        Args:
            election_id: Unique election identifier

        Returns:
            list of vote dictionaries
        """
        election = await self.get_election(election_id)
        if not election:
            return []

        votes = election.get("votes", {})
        return list(votes.values())

    async def delete_election(self, election_id: str) -> bool:
        """
        Delete an election from Redis.

        Args:
            election_id: Unique election identifier

        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.redis_client:
            logger.error("Redis client not connected")
            return False

        try:
            key = self._get_election_key(election_id)
            deleted = await self.redis_client.delete(key)

            return cast(int, deleted) > 0
        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to delete election {election_id}: {e}")
            return False

    async def update_election_status(self, election_id: str, status: str) -> bool:
        """
        Update election status.

        Args:
            election_id: Unique election identifier
            status: New status (e.g., "CLOSED", "EXPIRED")

        Returns:
            True if updated successfully, False otherwise
        """
        if not self.redis_client:
            return False

        try:
            election = await self.get_election(election_id)
            if not election:
                return False

            election["status"] = status

            key = self._get_election_key(election_id)
            ttl = await self.redis_client.ttl(key)
            if ttl <= 0:
                ttl = settings.voting.default_timeout_seconds

            serialized = self._serialize_election_data(election)
            json_str = json.dumps(serialized, default=str)
            await self.redis_client.setex(key, ttl, json_str)

            return True
        except (ConnectionError, OSError, TypeError, ValueError) as e:
            logger.error(f"Failed to update election {election_id} status: {e}")
            return False

    async def scan_elections(self, pattern: str | None = None) -> list[str]:
        """
        Scan for election IDs matching a pattern.

        Args:
            pattern: Optional pattern to match (defaults to all elections)

        Returns:
            list of election IDs
        """
        if not self.redis_client:
            return []

        try:
            search_pattern = pattern or f"{self.election_prefix}*"
            election_ids = []

            async for key in self.redis_client.scan_iter(match=search_pattern):
                # Remove prefix to get election_id
                election_id = key.replace(self.election_prefix, "")
                election_ids.append(election_id)

            return election_ids
        except (ConnectionError, OSError) as e:
            logger.error(f"Failed to scan elections: {e}")
            return []

    def _serialize_election_data(self, data: JSONDict) -> JSONDict:
        """Serialize election data for JSON storage."""
        serialized = data.copy()

        # Convert datetime objects to ISO format strings
        for key, value in serialized.items():
            if isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                serialized[key] = self._serialize_election_data(value)
            elif isinstance(value, list):
                serialized[key] = [
                    self._serialize_election_data(item) if isinstance(item, dict) else item
                    for item in value
                ]

        return serialized

    def _deserialize_election_data(self, data: JSONDict) -> JSONDict:
        """Deserialize election data from JSON storage."""
        deserialized = data.copy()

        # Convert ISO format strings back to datetime objects
        datetime_fields = ["created_at", "expires_at", "timestamp"]
        for key, value in deserialized.items():
            if key in datetime_fields and isinstance(value, str):
                try:
                    deserialized[key] = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            elif isinstance(value, dict):
                deserialized[key] = self._deserialize_election_data(value)
            elif isinstance(value, list):
                deserialized[key] = [
                    self._deserialize_election_data(item) if isinstance(item, dict) else item
                    for item in value
                ]

        return deserialized


# Singleton instance
_election_store: RedisElectionStore | None = None


async def get_election_store() -> RedisElectionStore:
    """Get singleton RedisElectionStore instance."""
    global _election_store
    if _election_store is None:
        _election_store = RedisElectionStore()
        await _election_store.connect()
    return _election_store
