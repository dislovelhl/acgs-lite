"""
ACGS-2 LangGraph Orchestration - State Persistence
Constitutional Hash: 608508a9bd224290

State persistence for graph orchestration:
- In-memory persistence for testing
- Redis persistence for production
- Checkpoint persistence and recovery
- State versioning and history
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

from .models import (
    Checkpoint,
    CheckpointStatus,
    ExecutionResult,
    ExecutionStatus,
    GraphState,
    StateSnapshot,
)

logger = get_logger(__name__)


class StatePersistence(ABC):
    """Abstract base class for state persistence.

    Constitutional Hash: 608508a9bd224290
    """

    @abstractmethod
    async def save_state(
        self,
        workflow_id: str,
        run_id: str,
        state: GraphState,
        node_id: str,
        step_index: int,
    ) -> str:
        """Save state snapshot.

        Args:
            workflow_id: Workflow identifier
            run_id: Run identifier
            state: State to save
            node_id: Current node ID
            step_index: Current step index

        Returns:
            Snapshot ID
        """
        ...

    @abstractmethod
    async def load_state(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> GraphState | None:
        """Load latest state for workflow.

        Args:
            workflow_id: Workflow identifier
            run_id: Optional specific run ID

        Returns:
            State if found, None otherwise
        """
        ...

    @abstractmethod
    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint.

        Args:
            checkpoint: Checkpoint to save
        """
        ...

    @abstractmethod
    async def load_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Load a checkpoint by ID.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            Checkpoint if found, None otherwise
        """
        ...

    @abstractmethod
    async def list_checkpoints(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> list[Checkpoint]:
        """List checkpoints for a workflow.

        Args:
            workflow_id: Workflow identifier
            run_id: Optional specific run ID

        Returns:
            List of checkpoints
        """
        ...

    @abstractmethod
    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint.

        Args:
            checkpoint_id: Checkpoint identifier

        Returns:
            True if deleted
        """
        ...

    @abstractmethod
    async def save_execution_result(self, result: ExecutionResult) -> None:
        """Save execution result.

        Args:
            result: Execution result to save
        """
        ...

    @abstractmethod
    async def load_execution_result(
        self,
        workflow_id: str,
        run_id: str,
    ) -> ExecutionResult | None:
        """Load execution result.

        Args:
            workflow_id: Workflow identifier
            run_id: Run identifier

        Returns:
            Execution result if found
        """
        ...


class InMemoryStatePersistence(StatePersistence):
    """In-memory state persistence for testing and development.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, constitutional_hash: str = CONSTITUTIONAL_HASH):
        self.constitutional_hash = constitutional_hash
        self._snapshots: dict[str, StateSnapshot] = {}
        self._checkpoints: dict[str, Checkpoint] = {}
        self._results: dict[str, ExecutionResult] = {}
        self._workflow_states: dict[str, list[str]] = {}  # workflow_id -> [snapshot_ids]

    async def save_state(
        self,
        workflow_id: str,
        run_id: str,
        state: GraphState,
        node_id: str,
        step_index: int,
    ) -> str:
        """Save state snapshot to memory."""
        import uuid

        snapshot = StateSnapshot(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            state=state,
            node_id=node_id,
            step_index=step_index,
            constitutional_hash=self.constitutional_hash,
        )

        self._snapshots[snapshot.id] = snapshot

        # Track by workflow
        if workflow_id not in self._workflow_states:
            self._workflow_states[workflow_id] = []
        self._workflow_states[workflow_id].append(snapshot.id)

        return snapshot.id

    async def load_state(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> GraphState | None:
        """Load latest state from memory."""
        snapshot_ids = self._workflow_states.get(workflow_id, [])
        if not snapshot_ids:
            return None

        # Get latest snapshot
        latest_id = snapshot_ids[-1]
        snapshot = self._snapshots.get(latest_id)
        return snapshot.state if snapshot else None

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to memory."""
        self._checkpoints[checkpoint.id] = checkpoint

    async def load_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Load checkpoint from memory."""
        return self._checkpoints.get(checkpoint_id)

    async def list_checkpoints(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> list[Checkpoint]:
        """List checkpoints from memory."""
        checkpoints = [
            cp
            for cp in self._checkpoints.values()
            if cp.workflow_id == workflow_id and (run_id is None or cp.run_id == run_id)
        ]
        return sorted(checkpoints, key=lambda c: c.created_at)

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete checkpoint from memory."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            return True
        return False

    async def save_execution_result(self, result: ExecutionResult) -> None:
        """Save execution result to memory."""
        key = f"{result.workflow_id}:{result.run_id}"
        self._results[key] = result

    async def load_execution_result(
        self,
        workflow_id: str,
        run_id: str,
    ) -> ExecutionResult | None:
        """Load execution result from memory."""
        key = f"{workflow_id}:{run_id}"
        return self._results.get(key)

    def clear(self) -> None:
        """Clear all stored data."""
        self._snapshots.clear()
        self._checkpoints.clear()
        self._results.clear()
        self._workflow_states.clear()


class RedisStatePersistence(StatePersistence):
    """Redis-based state persistence for production.

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "acgs2:langgraph:",
        ttl_seconds: int = 86400,  # 24 hours
        constitutional_hash: str = CONSTITUTIONAL_HASH,
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.ttl_seconds = ttl_seconds
        self.constitutional_hash = constitutional_hash
        self._redis: object | None = None

    async def _get_redis(self) -> object:
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(self.redis_url)
            except ImportError:
                logger.warning("redis package not installed, using fallback")
                raise RuntimeError("Redis not available") from None

        return self._redis

    def _state_key(self, workflow_id: str, run_id: str) -> str:
        """Generate key for state storage."""
        return f"{self.key_prefix}state:{workflow_id}:{run_id}"

    def _checkpoint_key(self, checkpoint_id: str) -> str:
        """Generate key for checkpoint storage."""
        return f"{self.key_prefix}checkpoint:{checkpoint_id}"

    def _result_key(self, workflow_id: str, run_id: str) -> str:
        """Generate key for result storage."""
        return f"{self.key_prefix}result:{workflow_id}:{run_id}"

    def _workflow_checkpoints_key(self, workflow_id: str) -> str:
        """Generate key for workflow checkpoints index."""
        return f"{self.key_prefix}checkpoints:{workflow_id}"

    async def save_state(
        self,
        workflow_id: str,
        run_id: str,
        state: GraphState,
        node_id: str,
        step_index: int,
    ) -> str:
        """Save state to Redis."""
        import uuid

        redis = await self._get_redis()

        snapshot = StateSnapshot(
            id=str(uuid.uuid4()),
            workflow_id=workflow_id,
            state=state,
            node_id=node_id,
            step_index=step_index,
            constitutional_hash=self.constitutional_hash,
        )

        key = self._state_key(workflow_id, run_id)
        data = json.dumps(
            {
                "id": snapshot.id,
                "workflow_id": workflow_id,
                "state": state.model_dump(),
                "node_id": node_id,
                "step_index": step_index,
                "created_at": snapshot.created_at.isoformat(),
                "constitutional_hash": self.constitutional_hash,
            }
        )

        await redis.setex(key, self.ttl_seconds, data)
        return snapshot.id

    async def load_state(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> GraphState | None:
        """Load state from Redis."""
        redis = await self._get_redis()

        if run_id:
            key = self._state_key(workflow_id, run_id)
            data = await redis.get(key)
            if data:
                parsed = json.loads(data)
                return GraphState(**parsed["state"])
        else:
            # Find latest run
            pattern = f"{self.key_prefix}state:{workflow_id}:*"
            keys = []
            async for key in redis.scan_iter(pattern):
                keys.append(key)

            if not keys:
                return None

            # Get most recent
            pipeline = redis.pipeline()
            for key in keys:
                pipeline.get(key)
            results = await pipeline.execute()

            latest = None
            latest_time = None
            for data in results:
                if data:
                    parsed = json.loads(data)
                    created = datetime.fromisoformat(parsed["created_at"])
                    if latest_time is None or created > latest_time:
                        latest = parsed
                        latest_time = created

            if latest:
                return GraphState(**latest["state"])

        return None

    async def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Save checkpoint to Redis."""
        redis = await self._get_redis()

        key = self._checkpoint_key(checkpoint.id)
        data = json.dumps(
            {
                "id": checkpoint.id,
                "workflow_id": checkpoint.workflow_id,
                "run_id": checkpoint.run_id,
                "node_id": checkpoint.node_id,
                "step_index": checkpoint.step_index,
                "state": checkpoint.state.model_dump(),
                "status": checkpoint.status.value,
                "constitutional_validated": checkpoint.constitutional_validated,
                "maci_validated": checkpoint.maci_validated,
                "created_at": checkpoint.created_at.isoformat(),
                "validated_at": (
                    checkpoint.validated_at.isoformat() if checkpoint.validated_at else None
                ),
                "metadata": checkpoint.metadata,
                "constitutional_hash": checkpoint.constitutional_hash,
            }
        )

        await redis.setex(key, self.ttl_seconds, data)

        # Add to workflow index
        index_key = self._workflow_checkpoints_key(checkpoint.workflow_id)
        await redis.zadd(
            index_key,
            {checkpoint.id: checkpoint.created_at.timestamp()},
        )
        await redis.expire(index_key, self.ttl_seconds)

    async def load_checkpoint(self, checkpoint_id: str) -> Checkpoint | None:
        """Load checkpoint from Redis."""
        redis = await self._get_redis()

        key = self._checkpoint_key(checkpoint_id)
        data = await redis.get(key)

        if not data:
            return None

        parsed = json.loads(data)
        return Checkpoint(
            id=parsed["id"],
            workflow_id=parsed["workflow_id"],
            run_id=parsed["run_id"],
            node_id=parsed["node_id"],
            step_index=parsed["step_index"],
            state=GraphState(**parsed["state"]),
            status=CheckpointStatus(parsed["status"]),
            constitutional_validated=parsed["constitutional_validated"],
            maci_validated=parsed["maci_validated"],
            created_at=datetime.fromisoformat(parsed["created_at"]),
            validated_at=(
                datetime.fromisoformat(parsed["validated_at"]) if parsed["validated_at"] else None
            ),
            metadata=parsed["metadata"],
            constitutional_hash=parsed["constitutional_hash"],
        )

    async def list_checkpoints(
        self,
        workflow_id: str,
        run_id: str | None = None,
    ) -> list[Checkpoint]:
        """List checkpoints from Redis."""
        redis = await self._get_redis()

        index_key = self._workflow_checkpoints_key(workflow_id)
        checkpoint_ids = await redis.zrange(index_key, 0, -1)

        checkpoints = []
        for cp_id in checkpoint_ids:
            if isinstance(cp_id, bytes):
                cp_id = cp_id.decode()
            checkpoint = await self.load_checkpoint(cp_id)
            if checkpoint:
                if run_id is None or checkpoint.run_id == run_id:
                    checkpoints.append(checkpoint)

        return checkpoints

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete checkpoint from Redis."""
        redis = await self._get_redis()

        key = self._checkpoint_key(checkpoint_id)
        deleted = await redis.delete(key)

        # Remove from all workflow indexes
        pattern = f"{self.key_prefix}checkpoints:*"
        async for index_key in redis.scan_iter(pattern):
            await redis.zrem(index_key, checkpoint_id)

        return deleted > 0  # type: ignore[no-any-return]

    async def save_execution_result(self, result: ExecutionResult) -> None:
        """Save execution result to Redis."""
        redis = await self._get_redis()

        key = self._result_key(result.workflow_id, result.run_id)
        data = json.dumps(
            {
                "workflow_id": result.workflow_id,
                "run_id": result.run_id,
                "status": result.status.value,
                "final_state": result.final_state.model_dump() if result.final_state else None,
                "output": result.output,
                "error": result.error,
                "total_execution_time_ms": result.total_execution_time_ms,
                "node_count": result.node_count,
                "step_count": result.step_count,
                "p50_node_time_ms": result.p50_node_time_ms,
                "p99_node_time_ms": result.p99_node_time_ms,
                "constitutional_validated": result.constitutional_validated,
                "checkpoint_count": result.checkpoint_count,
                "started_at": result.started_at.isoformat() if result.started_at else None,
                "completed_at": result.completed_at.isoformat(),
                "constitutional_hash": result.constitutional_hash,
            }
        )

        await redis.setex(key, self.ttl_seconds, data)

    async def load_execution_result(
        self,
        workflow_id: str,
        run_id: str,
    ) -> ExecutionResult | None:
        """Load execution result from Redis."""
        redis = await self._get_redis()

        key = self._result_key(workflow_id, run_id)
        data = await redis.get(key)

        if not data:
            return None

        parsed = json.loads(data)
        return ExecutionResult(
            workflow_id=parsed["workflow_id"],
            run_id=parsed["run_id"],
            status=ExecutionStatus(parsed["status"]),
            final_state=GraphState(**parsed["final_state"]) if parsed["final_state"] else None,
            output=parsed["output"],
            error=parsed["error"],
            total_execution_time_ms=parsed["total_execution_time_ms"],
            node_count=parsed["node_count"],
            step_count=parsed["step_count"],
            p50_node_time_ms=parsed["p50_node_time_ms"],
            p99_node_time_ms=parsed["p99_node_time_ms"],
            constitutional_validated=parsed["constitutional_validated"],
            checkpoint_count=parsed["checkpoint_count"],
            started_at=(
                datetime.fromisoformat(parsed["started_at"]) if parsed["started_at"] else None
            ),
            completed_at=datetime.fromisoformat(parsed["completed_at"]),
            constitutional_hash=parsed["constitutional_hash"],
        )

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


def create_state_persistence(
    backend: str = "memory",
    redis_url: str | None = None,
    **kwargs: object,
) -> StatePersistence:
    """Factory function to create state persistence.

    Args:
        backend: Persistence backend (memory, redis)
        redis_url: Redis URL for redis backend
        **kwargs: Additional configuration

    Returns:
        Configured state persistence

    Constitutional Hash: 608508a9bd224290
    """
    constitutional_hash = kwargs.pop("constitutional_hash", CONSTITUTIONAL_HASH)

    if backend == "memory":
        return InMemoryStatePersistence(constitutional_hash=constitutional_hash)
    elif backend == "redis":
        return RedisStatePersistence(
            redis_url=redis_url or "redis://localhost:6379",
            constitutional_hash=constitutional_hash,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown persistence backend: {backend}")


__all__ = [
    "InMemoryStatePersistence",
    "RedisStatePersistence",
    "StatePersistence",
    "create_state_persistence",
]
